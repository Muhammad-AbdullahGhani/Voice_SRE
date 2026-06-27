import logging
import asyncio
import uuid
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

from livekit.agents import JobContext, WorkerOptions, WorkerType, job_runner, llm
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import openai, silero
from langchain_core.messages import HumanMessage
from app.agents.supervisor import agent_graph

logger = logging.getLogger("livekit-sre-agent")

# --- CUSTOM LANGGRAPH LLM FOR LIVEKIT ---
class LangGraphLLM(llm.LLM):
    def __init__(self):
        super().__init__()
        # Generate a thread ID for the session
        self.thread_id = str(uuid.uuid4())
        
    def chat(self, *, chat_ctx: llm.ChatContext, fwd_messages: list = None) -> "LangGraphLLMStream":
        logger.info(f"New chat turn. Context length: {len(chat_ctx.messages)}")
        return LangGraphLLMStream(chat_ctx, self.thread_id)


class LangGraphLLMStream(llm.LLMStream):
    def __init__(self, chat_ctx: llm.ChatContext, thread_id: str):
        super().__init__()
        self.chat_ctx = chat_ctx
        self.thread_id = thread_id
        self._queue = asyncio.Queue()
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            # Extract user query
            last_msg = self.chat_ctx.messages[-1]
            user_text = ""
            if isinstance(last_msg.content, str):
                user_text = last_msg.content
            elif isinstance(last_msg.content, list):
                # Handle compound message formats
                user_text = " ".join([m for m in last_msg.content if isinstance(m, str)])
            
            logger.info(f"Invoking SRE Agent Graph with text: '{user_text}'")
            
            # Prepare state dict
            initial_state = {
                "messages": [HumanMessage(content=user_text)]
            }
            config = {"configurable": {"thread_id": self.thread_id}}
            
            # Run LangGraph in a threadpool so it doesn't block the asyncio event loop
            output = await asyncio.to_thread(agent_graph.invoke, initial_state, config)
            voice_response = output.get("voice_synthesis", "I encountered an error executing that request.")
            
            logger.info(f"SRE Agent synthesized voice response: '{voice_response}'")
            
            # Yield chunks to LiveKit VoiceAssistant TTS
            words = voice_response.split(" ")
            for i, word in enumerate(words):
                space = " " if i < len(words) - 1 else ""
                chunk = llm.ChatChunk(
                    choices=[
                        llm.Choice(
                            delta=llm.ChoiceDelta(
                                content=word + space,
                                role="assistant"
                            )
                        )
                    ]
                )
                self._queue.put_nowait(chunk)
                await asyncio.sleep(0.04)  # Simulate human-like streaming chunk delivery

        except Exception as e:
            logger.error(f"Error in LangGraph SRE LLM execution: {e}")
            error_chunk = llm.ChatChunk(
                choices=[
                    llm.Choice(
                        delta=llm.ChoiceDelta(
                            content="I experienced an issue processing your request.",
                            role="assistant"
                        )
                    )
                ]
            )
            self._queue.put_nowait(error_chunk)
        finally:
            # Signal stream end
            self._queue.put_nowait(None)

    async def __anext__(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def aclose(self):
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass


# --- LIVEKIT WORKER ENTRYPOINT ---
async def entrypoint(ctx: JobContext):
    logger.info(f"Agent job started for room: {ctx.room.name}")
    
    # Connect to LiveKit room
    await ctx.connect()
    
    # Initialize components
    # We use Silero for VAD and OpenAI Whisper/TTS for voice streaming
    assistant = VoiceAssistant(
        vad=silero.VAD.load(),
        stt=openai.STT(),
        llm=LangGraphLLM(),
        tts=openai.TTS(),
        chat_ctx=llm.ChatContext()
    )
    
    # Start voice assistant in the room
    assistant.start(ctx.room)
    logger.info("Voice SRE Supervisor is active in the room.")
    
    # Stay active until participant leaves
    await asyncio.sleep(86400)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Start LiveKit Agent worker CLI
    job_runner.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
        )
    )

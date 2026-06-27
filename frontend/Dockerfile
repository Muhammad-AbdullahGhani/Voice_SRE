FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Build Next.js
RUN npm run build

EXPOSE 3000

ENV PORT=3000 \
    NODE_ENV=production

CMD ["npm", "run", "start"]

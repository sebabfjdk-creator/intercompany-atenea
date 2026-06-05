# Frontend React/Vite — Intercompany Atenea
FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

# Dev server. Para producción: `npm run build` + servir /dist con nginx.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

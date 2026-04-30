FROM node:20-alpine AS build

WORKDIR /app
ARG VITE_BOT_URL=https://t.me/YOUR_BOT_USERNAME
ENV VITE_BOT_URL=$VITE_BOT_URL

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

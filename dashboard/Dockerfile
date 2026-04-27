FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --frozen-lockfile

COPY . .

ARG VITE_API_KEY
ENV VITE_BASE_PATH=/dashboard/
ENV VITE_API_KEY=$VITE_API_KEY
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html/dashboard
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

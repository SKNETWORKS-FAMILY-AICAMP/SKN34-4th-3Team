FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# frontend nginx 가 /ppt/ 로 프록시한다. 번들 asset 경로를 그 접두사에 맞춰 빌드한다.
RUN npm run build -- --base /ppt/

FROM nginx:1.29-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

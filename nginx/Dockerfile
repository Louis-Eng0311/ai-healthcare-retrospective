FROM node:20-alpine AS build

WORKDIR /frontend

COPY ./frontend/package.json ./frontend/package-lock.json ./
RUN npm ci

COPY ./frontend .
RUN npm run build

FROM nginx:alpine

# nginx 기본 html 경로에 복사
COPY --from=build /frontend/dist /usr/share/nginx/html
COPY ./nginx/default.conf /etc/nginx/conf.d/default.conf

CMD ["nginx", "-g", "daemon off;"]

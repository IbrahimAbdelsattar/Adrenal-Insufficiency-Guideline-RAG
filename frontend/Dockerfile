# Frontend service (Next.js). Dev image driven by docker-compose, hot-reloading
# against a bind-mounted source tree. For production, the app collapses into the
# root Dockerfile instead (static export served by FastAPI) rather than running
# this container.
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]

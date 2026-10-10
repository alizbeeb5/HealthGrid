# Development image; make a production image when deployment is scoped.
FROM node:22-bookworm-slim
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

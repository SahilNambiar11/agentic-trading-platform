# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci


FROM node:22-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY

ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL}" \
    NEXT_PUBLIC_SUPABASE_URL="${NEXT_PUBLIC_SUPABASE_URL}" \
    NEXT_PUBLIC_SUPABASE_ANON_KEY="${NEXT_PUBLIC_SUPABASE_ANON_KEY}"

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

RUN node -e 'const required=["NEXT_PUBLIC_API_BASE_URL","NEXT_PUBLIC_SUPABASE_URL","NEXT_PUBLIC_SUPABASE_ANON_KEY"]; for (const name of required) { const value=process.env[name] ?? ""; if (!value || value === "REPLACE_ME") throw new Error(`${name} is not configured`); } new URL(process.env.NEXT_PUBLIC_API_BASE_URL); const supabaseUrl=new URL(process.env.NEXT_PUBLIC_SUPABASE_URL); if (supabaseUrl.protocol !== "https:") throw new Error("NEXT_PUBLIC_SUPABASE_URL must use HTTPS");' \
    && npm run build


FROM node:22-alpine AS runtime

ENV HOSTNAME=0.0.0.0 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

WORKDIR /app

RUN addgroup --system --gid 10001 nextjs \
    && adduser --system --uid 10001 --ingroup nextjs nextjs

COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "const net=require('node:net');const socket=net.connect(3000,'127.0.0.1');socket.setTimeout(3000);socket.on('connect',()=>{socket.end();process.exit(0)});socket.on('timeout',()=>process.exit(1));socket.on('error',()=>process.exit(1))"]

CMD ["node", "server.js"]

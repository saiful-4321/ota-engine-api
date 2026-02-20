-- Users Table
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    name VARCHAR(155) NOT NULL,
    username VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    mobile VARCHAR(15),
    password VARCHAR(255) NOT NULL,
    access_token VARCHAR(255) UNIQUE,
    status BOOLEAN NOT NULL DEFAULT TRUE,
    user_role VARCHAR(20) NOT NULL DEFAULT 'user',
    last_login TIMESTAMP,
    last_logged_ip VARCHAR(45),
    created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NULL
);

-- User Login activity table
CREATE SEQUENCE "public"."login_activity_id_seq"
   START WITH 1
   INCREMENT BY 1
   MINVALUE 1
   MAXVALUE 2147483647
   CACHE 1;
CREATE TABLE "public"."login_activity"(
   "id" integer DEFAULT nextval('public.login_activity_id_seq'::regclass) NOT NULL,
   "login_date" character varying,
   "username" character varying,
   "user_role" character varying,
   "name" character varying,
   "ip" character varying,
   "location" character varying,
   "browser" character varying,
   "os" character varying,
   "device" character varying,
   "attempt" integer DEFAULT 0,
   "conn_number" integer DEFAULT 0,
   "remarks" character varying,
   "date" character varying,
   CONSTRAINT "login_activity_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "login_activity_username_key" ON "public"."login_activity" ("username");

-- User Tokens table
CREATE SEQUENCE "public"."user_tokens_id_seq"
   START WITH 1
   INCREMENT BY 1
   MINVALUE 1
   MAXVALUE 9223372036854775807
   CACHE 1;
CREATE TABLE "public"."user_tokens"(
   "id" bigint DEFAULT nextval('public.user_tokens_id_seq'::regclass) NOT NULL,
   "username" character varying NOT NULL,
   "user_id" integer NOT NULL,
   "token" character varying,
   "refresh_token" character varying,
   "status" character varying DEFAULT 'Valid'::character varying NOT NULL,
   "expires_at" character varying,
   "created_at" timestamp with time zone DEFAULT now() NOT NULL,
   "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
   CONSTRAINT "user_tokens_pkey" PRIMARY KEY ("id")
);

-- User IP table
CREATE TABLE public.user_ips (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    ip_address TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Create an index for faster IP lookups
CREATE INDEX user_ips_user_id_idx ON public.user_ips (user_id);
CREATE INDEX user_ips_ip_address_idx ON public.user_ips (ip_address);


-- API LOGS table
CREATE TABLE api_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    method VARCHAR(10) NOT NULL,
    url TEXT NOT NULL,
    client_ip VARCHAR(45),
    headers JSONB,
    query_params JSONB,
    request_body TEXT,
    user_agent TEXT,
    response_status INT NOT NULL,
    response_size INT,
    response_body TEXT,
    process_time DECIMAL(10,4) NOT NULL
);
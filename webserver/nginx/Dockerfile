FROM nginx:1.16.1

RUN apt-get update && apt-get install -qq -y \
  nginx-extras --no-install-recommends

RUN service nginx start
ARG BASE_IMAGE=ghcr.io/immich-app/immich-server:v3.2.4
FROM ${BASE_IMAGE}
LABEL org.opencontainers.image.version="3.2.4-koda.1" \
      com.mykodahome.koda.metadata-fix="1"
WORKDIR /usr/src/app/server
RUN node -e "if(require('./package.json').version !== '3.2.4') throw new Error('Koda patch requires Immich 3.2.4')"
COPY overlay/ ./dist/
COPY BUILD.json /opt/koda-metadata-fix/BUILD.json
RUN node --check dist/services/metadata.service.js && \
    node --check dist/services/storage-template.service.js && \
    node -e "require('./dist/utils/asset-metadata-lock.js'); require('./dist/repositories/database.repository.js')"
WORKDIR /usr/src/app

FROM nginx:1.25-alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY assets /usr/share/nginx/html/assets

# Asegura que el worker de nginx pueda leer/traversar /assets (evita 403 por permisos heredados del repo).
RUN chmod -R a+rX /usr/share/nginx/html/assets

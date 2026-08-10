# Static files only -- no build step, no bundler, no node_modules.
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html style.css api.js app.js /usr/share/nginx/html/

EXPOSE 80

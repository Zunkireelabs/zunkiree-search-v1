# Static HTML — no build step (matches vercel.json: "buildCommand": null).
FROM nginx:alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY privacy-policy.html terms-of-service.html data-deletion.html oauth-callback.html /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

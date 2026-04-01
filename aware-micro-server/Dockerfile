FROM eclipse-temurin:11-jre
WORKDIR /app

COPY output/micro-1.0.0-SNAPSHOT-fat.jar app.jar
COPY cache/ cache/

RUN useradd -r -s /bin/false appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080 8081
CMD ["java", "-jar", "app.jar"]

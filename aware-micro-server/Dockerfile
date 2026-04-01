FROM gradle:8.3-jdk11 AS build
WORKDIR /app

COPY build.gradle settings.gradle gradle.properties gradle.lockfile ./
COPY gradle/ gradle/
COPY gradlew .
RUN sed -i 's/\r$//' gradlew && chmod +x gradlew
RUN gradle dependencies --no-daemon

COPY src/ src/
COPY cache/ cache/

RUN gradle shadowJar --no-daemon

FROM eclipse-temurin:11-jre
WORKDIR /app

COPY --from=build /app/build/libs/*-fat.jar ./app.jar
COPY --from=build /app/cache ./cache

RUN useradd -r -m -s /bin/false appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080 8081
CMD ["java", "-jar", "app.jar"]

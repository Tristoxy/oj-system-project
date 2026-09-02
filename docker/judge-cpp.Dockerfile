FROM gcc:13

RUN useradd --create-home --uid 10001 judge
USER judge
WORKDIR /workspace

ENTRYPOINT []

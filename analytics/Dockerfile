FROM alpine:3.22
RUN apk add --no-cache goaccess python3 py3-google-auth py3-requests tzdata
WORKDIR /app
COPY report.py /app/report.py
ENTRYPOINT ["python3", "/app/report.py"]
CMD ["collect", "--logs", "/logs", "--database", "/data/traffic.sqlite3", "--reports", "/data/reports"]

- Start Postgres container
```
docker run -d --name agent-m-postgres -e POSTGRES_USER=agent-m-user -e POSTGRES_PASSWORD=agent-m-password -e POSTGRES_DB=agentm -p 5432:5432 postgres:17-alpine
```


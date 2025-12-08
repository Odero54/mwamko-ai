# MWAMKO AI API

## Build and run docker containers

To build and run the app docker containers, follow these steps:

1. Clone the repository and navigate to the project directory:

    ```bash
    git clone git@github.com:Odero54/mwamko-ai.git
    cd mwamko-ai
    ```

2. Build and run the Docker containers:

     ```bash
     docker compose up -d --build
     ```

3. To bring down the containers and the volumes, run:

     ```bash
     docker compose down -v
     ```

## Running the Database Only

To run only the PostgreSQL database locally:

```bash
# Run only the database service
docker compose --profile app up -d db

# Or run with specific service
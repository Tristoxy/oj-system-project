# Python Course OJ

A small Online Judge system implemented incrementally with FastAPI.

The current version includes the common API foundation and Step 1 problem
management backed by one JSON file per problem.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` to check the service, or
`http://127.0.0.1:8000/docs` to view FastAPI's interactive API documentation.

## Run tests

```bash
pytest
```

## Step 1 API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/problems/` | List problem IDs and titles |
| `POST` | `/api/problems/` | Validate and create a problem |
| `GET` | `/api/problems/{problem_id}` | Read full problem details |
| `DELETE` | `/api/problems/{problem_id}` | Delete a problem |

Problem files are created under `data/problems/` while the service is running.
Runtime data is ignored by Git.

Authentication and administrator checks are introduced in Step 4. At that
stage, the Step 1 routes will be updated to enforce the final API permissions.

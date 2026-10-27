Thank you for considering contributing!

- Fork the repository and open a pull request.
- Keep changes focused and small; one feature or fix per PR.
- Run tests and linters before submitting. These are the checks CI runs:

  ```sh
  pip install -r requirements.txt
  python -m unittest -v \
    tests.test_phase1_decoupling tests.test_hosted_api tests.test_core_resilience \
    tests.test_qa_system tests.test_api_key_validation tests.test_action_helpers
  cd web && npm ci && npm run typecheck && npm run lint && npm run build
  ```

  Backend tests use SQLite and in-memory rate limits unless `DATABASE_URL` and
  `REDIS_URL` are set; CI runs them against Postgres and Redis.
- Update `README.md` or docs for any user-visible changes.

If you find an accidental secret, notify the maintainers immediately and do not share the secret in public.

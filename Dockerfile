# Sandbox image used to evaluate untrusted student code.
#
# The container is started with:
#   docker run --rm --network none --memory 256m --cpus 0.5 -v <workdir>:/app sandbox-evaluador
#
# The working directory contains exactly two files:
#   exercise_student.py  — the solution uploaded by the student
#   test_exercise.py     — the hidden test suite
FROM python:3.12-alpine

WORKDIR /app

# pytest plus the plugin that writes the structured JSON report.
RUN pip install --no-cache-dir pytest pytest-json-report

# The report is written inside the mounted workspace so the host can read it.
CMD ["pytest", "test_exercise.py", "--json-report", "--json-report-file=report.json"]

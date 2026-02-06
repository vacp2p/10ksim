.PHONY: format check install-hooks

install-hooks: mkdir -p .git/hooks cp hooks/pre-push .git/hooks/pre-push chmod +x .git/hooks/pre-push

format:
	autoflake --in-place --remove-all-unused-imports --recursive .
	isort --profile black -l 100 .
	black -l 100 .

check:
	./check_format.sh
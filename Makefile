BLUE='\033[0;34m'
NC='\033[0m' # No Color

update-cdk:
	cd iot-playground;
	pip install --upgrade aws-cdk.core;
	cd -;

restart-env:
	cd iot-playground;
	python3 -m venv .env;
	source .env/bin/activate.fish;
	pip install -r requirements.txt;
	cd -;

lint:
	@echo "\n${BLUE}Running Pylint against source and test files...${NC}\n"
	@pylint --rcfile=setup.cfg **/*.py
	@echo "\n${BLUE}Running Flake8 against source and test files...${NC}\n"
	@flake8
	@echo "\n${BLUE}Running Bandit against source files...${NC}\n"
	@bandit -r --ini setup.cfg
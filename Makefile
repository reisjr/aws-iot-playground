BLUE='\033[0;34m'
NC='\033[0m' # No Color

create-cdk-env:
	python3 -m venv cdk/.env;
	cd cdk && source .env/bin/activate && pip install -r requirements.txt;

update-cdk:
	cd cdk && source .env/bin/activate && pip install --upgrade aws-cdk.core;

deploy-stack:
	cd cdk && source .env/bin/activate && cdk deploy iot-playground codepipeline devicedefender --require-approval never;

deploy-cdk-bootstrap:
	# aws sts get-caller-identity --query "Account" --output text >> .iot-playground.cfg
	# cd cdk && source .env/bin/activate && cdk bootstrap "aws://$ACC_ID/us-east-1";
	./scripts/deploy-bootstrap.sh

lint:
	@echo "\n${BLUE}Running Pylint against source and test files...${NC}\n"
	@pylint --rcfile=setup.cfg **/*.py
	@echo "\n${BLUE}Running Flake8 against source and test files...${NC}\n"
	@flake8
	@echo "\n${BLUE}Running Bandit against source files...${NC}\n"
	@bandit -r --ini setup.cfg
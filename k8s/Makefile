all: tester deploy

deploy:
	kubectl apply -f .

useradd:
	kubectl exec ds/north-netconf -- bash -c 'useradd admin && echo admin:admin | chpasswd'

bash:
	kubectl exec -it ds/gs-mgmt-tester -- bash

tester:
	sed -e s!HOSTPATH!$(abspath ../)!g template/tester.yaml > tester.yaml

clean:
	kubectl delete -f .

netconf-cli:
	kubectl exec -it ds/gs-mgmt-tester -- bash -c 'cd src/north/cli && PYTHONPATH=../../lib python -m goldstone.north.cli.main --connector netconf --connector-opts host=$$NORTH_NETCONF_SERVICE_HOST,username=admin,password=admin,hostkey_verify=false,schema_dir=schema -v'

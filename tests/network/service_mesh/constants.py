from ocp_resources.resource import Resource

SMMR_NAME = "default"
SERVER_DEMO_HOST = "server-demo.example.com"
SERVER_DEMO_NAME = "server-demo"
VERSION_2_DEPLOYMENT = "v2"
SERVER_DEPLOYMENT_STRATEGY = {
    "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 1},
    "type": "RollingUpdate",
}
SERVER_IMAGE = "quay.io/openshift-cnv/qe-cnv-service-mesh-server-demo"
SERVER_V1_IMAGE = f"{SERVER_IMAGE}:{Resource.ApiVersion.V1}.0"
SERVER_V2_IMAGE = f"{SERVER_IMAGE}:{VERSION_2_DEPLOYMENT}.0"
GATEWAY_SELECTOR = {"istio": "ingressgateway"}
HTTP_PROTOCOL = "HTTP"
SERVICE_TYPE = "service"
GATEWAY_TYPE = "gw"
DESTINATION_RULE_TYPE = "dr"
VIRTUAL_SERVICE_TYPE = "vs"
PEER_AUTHENTICATION_TYPE = "pa"
DEPLOYMENT_TYPE = "dp"
INGRESS_SERVICE = "istio-ingressgateway"

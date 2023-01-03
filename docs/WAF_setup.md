To-Do

- [x] Introduce App Service + WAF
- [ ] Write tutorial
  - [x] Link to tutorials on creating Application Gateway
  - [x] How to link app service into backend pool
  - [x] how to set up WAF in prevention mode
  - [x] add exception for Inference service
  - [ ] how to run tests from the Gateway

# OWASP-Compliant Inference Service

For increased security on your Inference service, you may want to deploy it behind an Application Gateway running a Web Application Firewall (WAF). WAFs can be configured to filter all traffic to and from your application service by ensuring it conforms to certain standards. This tutorial will detail how to set up an Inference Service behind a WAF enforcing the [OWASP 3.2 Core Rule Set (CRS)](https://learn.microsoft.com/en-us/azure/web-application-firewall/ag/application-gateway-crs-rulegroups-rules?tabs=owasp32#owasp-crs-30).

This tutorial assumes a basics familiarty with Application Gateways. You can read about them on [Microsft Learn](https://learn.microsoft.com/en-us/azure/application-gateway/overview#features) for a quick overview.

> *It should be noted that all traffic between the InnerEye-Gateway and InnerEye-Inference serivce is* already *OWASP compliant. This tutorial simply shows you how to set up a WAF that ensures any traffic coming from other sources also conforms to this standard, in order to reduce the risk of malicious traffic hitting your Inference service endpoints.*

## Steps

### 1. Create Application Gateway

Firstly, you will need to create an Application Gateway. This can be done by following the tutorial linked below, with 1 important change:

- **During the "Basics tab" section, select the tier "WAF", not the tier "WAF V2".**

While in theory the WAF V2 version should work perfectly well, it has not been tested by our team and we cannot guarantee functionality.

To set up your Application Gateway, carry out the steps in "Create an Application Gateway" in [this tutorial](https://learn.microsoft.com/en-us/azure/web-application-firewall/ag/application-gateway-web-application-firewall-portal#create-an-application-gateway), selecting a different tier as described above.

### 2. Create your Inference App Service

If you've not already done so, deploy your Inference App Service by following the steps in the [README](https://github.com/microsoft/InnerEye-Inference/#running-flask-app-in-azure).

### 3. Link Inference Service to Application Gateway Backend

Follow the steps in the "Add App Service as Backend Pool" section of [this tutorial](https://learn.microsoft.com/en-us/azure/application-gateway/configure-web-app?tabs=customdomain%2Cazure-portal#add-app-service-as-backend-pool)

Presuming you were successful with all the previous steps, you should now be able to see your App Service endpoint reporting as healthy under "Monitoring -> Backend Health" on your Application Gateway.

### 4. Set Up WAF

- In the Azure Portal, navigate to your newly created Gateway and select "Web Application Firewall" under "Settings" on the left side of the page.
- Ensure that the "WAF Mode" has been set to "Prevention".
- Under exclusions, add the following row:
  - Field = "Request neader name"
  - Operator = "Equals"
  - Selector = "Content-Type"

Your WAF page should now look like this:

![WAF setup image](./docs/../WAF_setup.png)

### 5. Test with InnerEye-Gateway



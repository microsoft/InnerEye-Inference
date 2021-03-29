# How to run end to end demo on local environment?

Here are some quick steps to run end to end demo on your local environment.

Do SSH into the GPU VM, first command is docker images to get the image id of the modified head and neck container. Then run it interactively using

1. Start the GPU VM which has Inferencing container. Get the public IP and copy it.
2. Do SSH to this VM using - SSH <userName>:IP address
3. If prompted enter "yes"
4. Now it will ask for password. Enter the password:
5. After successful login it will open the VM shell. In the shell run below command.
6. docker run -it --entrypoint=/bin/bash -p 8086:5000 -e AZURE_STORAGE_ACCOUNT_NAME=name -e AZURE_STORAGE_KEY=<accountKey> -e AZURE_STORAGE_ENDPOINT=<endpoint> --gpus all <image>
7. conda activate nnenv
8. python web-api.py
9. Clone https://github.com/microsoft/InnerEye-gateway 
10. Clone https://github.com/microsoft/InnerEye-inference 
11. Set platform to x64 and build the project
12. Generate self signed certificate using below command in PowerShell window. Make sure you run it as Administrator.
    `New-SelfSignedCertificate -CertStoreLocation Cert:\LocalMachine\My -DnsName "mysite.local" -FriendlyName "InnerEyeDryRun" -NotAfter (Get-Date).AddYears(10)`
13. Copy the thumbprint and replace "KeyVaultAuthCertThumbprint" key value of Inferencing API and Worker Project in config file.
    a. Microsoft.InnerEye.Azure.Segmentation.API.Console
    b. Microsoft.InnerEye.Azure.Segmentation.Worker.Console
14. Replace the other keys in same file.
15. Build both projects.
16. Now run both project Inferencing API and Engine exe. from bin directory
    a. Microsoft.InnerEye.Azure.Segmentation.Worker.Console.exe
    b. Microsoft.InnerEye.Azure.Segmentation.API.Console.exe
17. Next thing is to run gateway receiver and processor:
    a. Microsoft.InnerEye.Listener.Processor.exe
    b. Microsoft.InnerEye.Listener.Receiver.exe
18. Now you have to navigate to images folder
19. Open path in PowerShell window.
20. Run these command on PowerShell - `storescu 172.16.0.5 104 -v --scan-directories -aec RGPelvisCT -aet Scanner .`
21. Open a suitable path in PowerShell where you want to store result.
22. Run on powershell `storescp 1105 -v -aet PACS -od . --sort-on-study-uid st`
23. Wait for results.


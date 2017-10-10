# QlikPrivacyIntegration
An example implementation of Advanced Analytics Integration with Qlik for encrypting/decrypting data inside of a Qlik Application.

This is still a Work in Progress, however it is a good starting point.

Please see the "/QlikSense/QPI Overview.ppt" file for an overview.

## Setting up the example
#### Prerequisites:
1. Qlik Sense June/2017 (or later) - Requires AAI (Advanced Analytics Integration).
2. Working Docker Environment, should be able to run:<br>
  ```
  docker run hello-world
  ```
  <br>Example environments include:
  * Mac w/Docker
  * Windows with Docker Toolkit (typically, this is the best option because of Hyper-V conflicts with VirtualPC and/or VMWare)
  * Windows with either VirtualPC or VMWare image running Windows Docker
  * {last resort} Windows with either VirtualPC or VMWare image running an Ubuntu Docker image
3. Download and unzip this github project, into your environment that supports Docker.

#### Setup Docker Container
In your environment that supports Docker, using Terminal (Mac) or PowerSheel (Windows)...
1. Navigate to folder that you downloaded "this github project"<br>
  ```
  cd {github_project_download_path}/
  ```
  <br><br><b>NOTE: </b>The current directory should contain a file named: "docker-compose.yml"<br>&nbsp;
2. Run the following commands:<br>
  ```
  docker swarm init
  docker stack deploy -c docker-compose.yml qpi
  ```
    <br><br><b>NOTE 1: </b>You may need to use "docker swarm init --advertise-addr {ip_address of qpi hostmachine}" if using Windows7/docker-toolbox.
    <br><b>NOTE 2: </b>This may take awhile during the download.<br>&nbsp;
3. Run the following command:<br>
  ```
  docker run -it --rm -p 50054:50054 -v {github_project_download_path}/logs:/logs -v {github_project_download_path}/configs:/configs -v {github_project_download_path}/data:/data --name qpi newmans99/qpi:latest
  ```
  <br><br><b>WHERE:<br>{github_project_download_path} =</b> Fully qualified path to github project contents. This should start with /, //, or c:\ depending on your environment. This can not be a relative path, such as: "./" or "../"

#### Setup Qlik Sense
<b>In Qlik Sense QMC...</b>
1. QMC > Analytic connections > Create New ->
  * NAME: QPI
  * HOST: [IP Address of your Docker Container, see Docker setup above]
  * PORT [Default unless changed]: 50054
  * Others, leave as default
2. QMC > Apps > Import ->
  * Qlik Privacy Integration.qvf
  * Qlik Privacy Integration Log Analysis.qvf

<b>In Qlik Sense Hub...</b>
1. Hub > Work > Qlik Privacy Integration Log Analysis.qvf
2. Navigation > Data Load Editor
3. Create new connection >
  * Type: Folder
  * Path: [Path to QPI Log folder, see Docker setup above]<br><b>NOTE: </b>If your log director is on a different machine/container than where Qlik Sense is installed, you will have to setup a share before setting up the path.
  * Name: QPI_Audit Logs (qliksense_qlik)<br><b>NOTE: </b>If the connection "Name" is different than above, in the Load Script edit the variable value located: SECTION: QPI Audit Log Data, Line: 2, Variable Name: vQPILogConnectionName.
4. <b>NOTE: </b>You do not need to reload the app at this point, it has some sample data in it now.

<b>Lastly...</b>
1. Restart Qlik Sense or just the Qlik Sense Engine (while the Docker Container is running), this will register the QPI AAI function with the Qlik Sense Server.   

#### Test your Setup
<b>In Qlik Sense Hub...</b>
1. Open: Hub > Work > Qlik Privacy Integration
2. Navigate to "Encryption Results"
  * If everything is working, you should see: Patient Names/Phone Numbers in the "Decrypted Data..." table on the right side.
  * If you run into problems, please see Troubleshooting Section below.
3. Navigate to "getField() Results"
  * If everything is working, you will see patient names/numbers in both tables.
4. Open: Hub > Work > Qlik Privacy Integration Log Analysis
5. Navigate to "Log Analysis"
6. Make a few selections, to reduce the Record Count KPI (upper left corner) to a smaller number.
7. Click (twice) the KPI, to get the Log details
8. Reload Log data: Navigation > Data Load Editor (new window)
9. Reload button
10. Explore sheets

## Troubleshooting
* It has been reported that running Docker Toolkit inside of a VirtualPC/VMWare Image doesn't work. The work around is to use Docker Toolkit on your host operating system instead.

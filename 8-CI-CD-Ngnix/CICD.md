# Adding CI/CD to the Project


1- In the root of the project, create a file named `.github/workflows/deploy.yml` and add the following content:

```yaml
name: CI/CD

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PRIVATE_KEY }}

      - name: Deploy to production
        uses: matheusvanzan/sshpass-action@v2
        with:
          host: ${{ secrets.HOST }}
          user: ${{ secrets.MY_SECRET_NAME }}
          key: ${{ secrets.PRIVATE_KEY }}
          run: |
            cd ${{ secrets.PROJECT_PATH }}
            git pull origin main
            # Add additional deployment commands here
``` 

2- In your GitHub repository, go to `Settings` > `Secrets and variables` > `Actions` and add the following secrets: 

- `PRIVATE_KEY`: The private SSH key that has access to your server.
from the root if the VPS : 
```bash
cd ~/.ssh 
cat PRIVATE_KEY #(rsa or ed25519)
``` 
copy the content and paste it in the `PRIVATE_KEY` secret in GitHub.

- `HOST`: The IP address or hostname of your server.
- `MY_SECRET_NAME`: The username to access your server.
- `PROJECT_PATH`: The path to your project on the server.

3- In the root of the VPS naviagate to the project directory and run the following command to initialize a Git repository and push it to GitHub:

```bash
cd /path/to/your/project
git init
git clone <repository-url>
``` 

to make sure that the project is connected to the GitHub repository, you can run:

```bash
git remote -v
```

test the CI/CD pipeline by making a commit and pushing it to the `main` branch:

```bash
git add .
git commit -m "Test CI/CD pipeline"
git push origin main
``` 
This will trigger the GitHub Actions workflow, which will deploy your changes to the server automatically. You can check the workflow logs in the `Actions` tab of your GitHub repository to see the deployment process in action. 

## At this point we still launch the project from 7-Deployemnt_test (see the README.md in that folder) 
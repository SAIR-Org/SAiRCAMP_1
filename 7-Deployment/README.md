# Deployment on VPS: (our own server) 

# Note : YOU MUST HAVE AN ACCESS TO A VPS (Virtual Private Server) TO DEPLOY YOUR APPLICATION. 

you can refrenc this medium article : 
https://medium.com/@infosecnubes/ssh-key-based-authentication-5816d6238c2 

## Steps to deploy your application on a VPS:
1- generate a ssh key pair on your local machine: 
```bash
ssh-keygen -t ed25519 -C "@anything" 
``` 

ed25519 = a type of encryption algorithm that is more secure and faster than the traditional RSA algorithm.

other alternatives:
```bash
ssh-keygen -t rsa -b 4096 -C "
``` 
rsa = a widely used encryption algorithm that is based on the difficulty of factoring large integers. 

# if all go well you should see a message like this: 

```text
Generating public/private ed25519 key pair.
Enter file in which to save the key (~/.ssh/id_ed25519):
Enter passphrase (empty for no passphrase):
Enter same passphrase again:

Your identification has been saved in ~/.ssh/id_ed25519
Your public key has been saved in ~/.ssh/id_ed25519.pub

The key fingerprint is:
SHA256:<your-key-fingerprint>

The key's randomart image is:
+--[ED25519 256]--+
|       (example) |
|    random art   |
|      omitted    |
|      for docs   |
+----[SHA256]-----+ 

```

2- Copy the public key to the server : 
```bash
cat ~/.ssh/id_ed25519.pub 
```

3- Connect to the server using ssh and create a .ssh directory if it doesn't exist: 
```bash
nano ~/.ssh/authorized_keys
```

4- Access the server using ssh and paste the public key into the authorized_keys file: 
```bash 
ssh username@server_ip_address 
```

5- Generate a new SSH key pair on the server : 
```bash
ssh-keygen -t ed25519 -C "@anything" 
``` 

6- Create a config file inside .ssh folder to add configs for multiple GitHub repository authentication

```bash
git clone 
nano ~/.ssh/config 
``` 

```
Host <appname>
  HostName github.com
  User git
  IdentityFile ~/.ssh/<app_ssh_key_file_name> # ed25519.pub or rsa key file name
```


7- Copy the public key from the server github Deploy keys:

setting > Deploy keys > copy the public key from the server and paste it into the github deploy keys section.

8- Clone the repository using the SSH URL: 
```bash
git clone git@github.com:username/repository.git
``` 









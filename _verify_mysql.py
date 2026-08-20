import paramiko

HOST = '11.0.1.134'
USER = 'root'
PWD = '123456'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, 22, USER, PWD, timeout=10)

results = {}

def exec(cmd):
    _, stdout, _ = client.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

results['version'] = exec("mysql -u root -e 'SELECT VERSION();' 2>&1")
results['databases'] = exec("mysql -u root -e 'SHOW DATABASES;' 2>&1")
results['root_auth'] = exec("mysql -u root -e \"SELECT user, host, authentication_string!='' AS has_pwd, plugin FROM mysql.user WHERE user='root';\" 2>&1")
results['users'] = exec("mysql -u root -e 'SELECT user, host, plugin FROM mysql.user ORDER BY user;' 2>&1")
results['port_config'] = exec("mysql -u root -e \"SHOW VARIABLES LIKE 'port'; SHOW VARIABLES LIKE 'bind_address';\" 2>&1")
results['data_size'] = exec("du -sh /var/lib/mysql/ 2>&1")
results['enabled'] = exec("systemctl is-enabled mysqld 2>&1")
results['selinux'] = exec("ls -Z /var/lib/mysql/ 2>&1 | head -5; echo ---; getenforce 2>&1")
results['ping'] = exec("mysqladmin ping -u root 2>&1")
results['firewall'] = exec("firewall-cmd --list-ports 2>&1; echo ---; firewall-cmd --list-services 2>&1")
results['memory'] = exec("free -h 2>&1")
results['disk'] = exec("df -h /var/lib/mysql / 2>&1")
results['process'] = exec("ps aux | grep mysqld | grep -v grep")
results['config_file'] = exec("cat /etc/my.cnf.d/mysql-server.cnf 2>&1")

client.close()

for k, v in results.items():
    print(f'=== {k} ===')
    print(v)
    print()
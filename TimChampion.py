import sys,os
import paramiko
from quantumclient.v2_0 import client as quantumClient
from novaclient.v1_1 import client as novaClient

USER="localadmin"
PASSWORD="3r1cs50n"
host_dict={"ubuntu1":"10.175.150.3",
    "Ubuntu2":"10.175.150.5"}

def sshExec(ssh,cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    content = stdout.readlines()
    return content

def sshConnect(ip,username,passwd):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip,22,username,passwd,timeout=5)
        return ssh
    except :
        print '%s\tError\n'%(ip)
def sshClose(ssh):
    ssh.close()

def qbr2vm(qbr_id,ssh):
    command = "brctl showmacs qbr" + qbr_id + " 2>/dev/null | egrep \"^  2.*yes\" | cut -f2"
    qbr_mac = sshExec(ssh,command)
    if len(qbr_mac) == 0:
        return "None"
    else:
        match_mac = str(qbr_mac[0])[3:]
        return match_mac
def get_mac_qvo(qvolist,ssh):
    mac = []
    for qvo in qvolist:
        qbrid = str(qvo.strip('\n'))[3:]
        tmpmac = qbr2vm(qbrid,ssh)
        mac.append(tmpmac)
    return mac

def get_vlan_id(bridge,bridge_type,ssh):
    vlan_id = []
    command = "ovs-ofctl dump-flows " + bridge
    tmp = sshExec(ssh,command)
    for line in tmp:
        info = line.split(',')
        if len(info)==9 and info[7].startswith('dl_vlan'):
            ids = info[7].split()
            if bridge_type=="core" :
                dl_vlan = ids[0].split('=')
                vlan_id.append(dl_vlan[1].strip('\n'))
            else:
                dl_vlan = ids[1].split(':')
                if len(dl_vlan)>1:
                    vlan_id.append(dl_vlan[1].strip('\n'))
    return vlan_id

def popen_cmd(command):
    return os.popen(command).readlines()

def get_Bridge(ssh):
    return sshExec(ssh,"ovs-vsctl list-br")

def get_CoreBridge(bridgelist,ssh):
    CoreBrList = []
    for bridge in bridgelist:
        tmpstr = sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep phy-")

        if len(tmpstr) == 0:
            CoreBrList.append(bridge.strip('\n'))
    return CoreBrList

def get_PhyBridge(bridgelist,ssh):
    PhyBrList = []
    for bridge in bridgelist:
        tmpstr = sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep phy-")
        if len(tmpstr) != 0:
            PhyBrList.append(bridge.strip('\n'))
    return PhyBrList

def get_QvoList(bridge,ssh):
    return sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep qvo")
def get_intPort(bridge,ssh):
    return sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep int-")
def get_ethPort(bridge,ssh):
    return sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep eth |grep -v '\.'|grep -v 'phy-'")
def get_phyPort(bridge,ssh):
    return sshExec(ssh,"ovs-vsctl list-ports " + bridge.strip('\n') + " | grep phy- ")
def get_BR_Info():
    hosts = host_dict.keys()
    ips = host_dict.values()
    BRs = []
    ETHs = []
    for i in range(0,len(hosts)):
        ssh = sshConnect(ips[i],USER,PASSWORD)
        bridgelist = get_Bridge(ssh)
        for bridge in get_CoreBridge(bridgelist,ssh):
            tmpBR={}
            tmpBR["name"]=bridge
            tmpBR["host"]=hosts[i]
            tmpBR["qvo"]=get_QvoList(bridge,ssh)
            tmpBR["mac"]=get_mac_qvo(tmpBR["qvo"],ssh)
            tmpBR["int"]=get_intPort(bridge,ssh)
            tmpBR["vlan"]=get_vlan_id(bridge,"core",ssh)
            BRs.append(tmpBR)

        for bridge in get_PhyBridge(bridgelist,ssh):
            tmpETH={}
            tmpETH["name"]=bridge
            tmpETH["host"]=hosts[i]
            tmpPhy = get_phyPort(bridge,ssh)
            tmpETH["phy"]=tmpPhy[0].strip('\n')
            tmpEth = get_ethPort(bridge,ssh)
            tmpETH["eth"]=tmpEth[0].strip('\n')
            tmpETH["vlan"]=get_vlan_id(bridge,"phy",ssh)
            ETHs.append(tmpETH)
        sshClose(ssh)
    return BRs,ETHs

def read_config(config):
    prop = {}
    with open(config, 'rb') as propfile:
        for line in propfile:
            if line.startswith('#'): continue
            if line.startswith(" "): continue
            if line.find("=") == -1: continue
            (name,value) = line.split("=")
            if name.startswith("export "):  # used to align with another configuration files
                name = name.replace("export ","")
            value = value.strip() # remove space and endline
            value = value.strip('"')  # remove quote around value  "http://"
            prop[name]=value
    return prop

def set_global_data():
    global OS_USERNAME,OS_PASSWORD,OS_TENANT_NAME,OS_AUTH_URL
    OS_USERNAME="admin"
    OS_PASSWORD="admin"
    OS_TENANT_NAME="demo"
    OS_AUTH_URL="http://10.175.150.3:35357/v2.0"
'''
get Openstack client
'''
def get_quantum_client():
    nc = quantumClient.Client(username=OS_USERNAME, tenant_name=OS_TENANT_NAME,
                                 password=OS_PASSWORD, auth_url=OS_AUTH_URL, service_type="compute", no_cache=True)
    return nc
def get_nova_client():
    nc = novaClient.Client(OS_USERNAME, OS_PASSWORD, OS_TENANT_NAME, OS_AUTH_URL, service_type="compute", no_cache=True)
    return nc

def get_Net(networkList, netName):
    for network in networkList:
        if netName == network["name"]:
            return network
def get_Port(portList, ip):
    for port in portList:
        if port["fixed_ips"][0]["ip_address"] == ip:
            return port
def get_VM_Info():
    quantumclient = get_quantum_client()
    novaclient = get_nova_client()
    networklist = quantumclient.list_networks()
    portlist = quantumclient.list_ports()
    vmlist = novaclient.servers.list()

#    print "--------------------------------------------------------------------------------------------------------------------------------------"
#    fmt = "| %-20s | %-10s | %-20s | %-5s | %-5s |"
#    print fmt % ("VM","Status","MacAddress","type","segid")
    VMs = []
    for vm in vmlist:
        tmpvm = {}
        tmpvm["name"] = vm.name
        tmpvm["status"] = vm.status
        tmpvm["network"] = []
        vmNetworks = vm.networks
        for network in vmNetworks.items():
            tmpnetwork = get_Net(networklist["networks"],network[0])
            tmpport = get_Port(portlist["ports"],network[1][0])
            tmpvmnw = {}
            tmpvmnw["mac"] = tmpport["mac_address"]
            tmpvmnw["seg"] = tmpnetwork["provider:segmentation_id"]
            tmpvmnw["type"] = tmpnetwork["provider:network_type"]
            tmpvmnw["name"] = tmpnetwork["name"]
            tmpvmnw["phynet"] = tmpnetwork["provider:physical_network"]
            tmpvm["network"].append(tmpvmnw)
        VMs.append(tmpvm)
    return VMs
def get_qvo_id_from_BR(BRs,mac):
    for br in BRs:
        if len(br["mac"]) != 0:
            for i in range(0,len(br["mac"])):
                if str(br["mac"][i]).lower().strip("\n") == str(mac)[3:].lower().strip("\n"):
                    tmpqvo = br["qvo"][i]
                    tmpbr = br
                    tmphost = br["host"]
                    break

    return tmpqvo,tmpbr,tmphost

def get_phybri_from_eth(ETHs,vlan,host):
    tmpeth = []
    for eth in ETHs:
        if eth["host"].strip("\n") == host.strip("\n") and str(vlan).strip("\n") in eth["vlan"]:
            tmpeth.append(eth["eth"])
    return tmpeth

def get_phybri_flat(br,ETHs):
    phybri = []
    for intbreth in br["int"]:
        tmpphybri = "phy-" + intbreth[4:]
        for eth in ETHs:
            if br["host"].strip("\n") == eth["host"].strip("\n"):
                if tmpphybri.strip("\n") == eth["phy"].strip("\n"):
                    phybri.append(eth["eth"])
    return phybri

def initArr(col_len,row_len):
    array = [[0 for col in range(col_len)] for row in range(row_len)]
    return array

def processData(old):
    new = initArr(len(old[0]),len(old))
    for i in range(len(old)-1,0,-1):
        for j in range(len(old[0])):            
            if old[i][j]==old[i-1][j]:
                if j==0:
                    new[i][0] = 1
                else:
                    break
            else:
                new[i][j] = old[i][j][:]
    new[0][:] = old[0][:][:]
    
    for i in range(1,len(old)):
        for j in range(1,len(old[0])):
            if new[i][j-1]!=0 and new[i-1][j-1]==0:
                new[i][j] = old[i][j][:]
    #print new
    return new

def getLen(data):
    lens = initArr(len(data[0]),len(data))
    for i in range(len(data)):
        for j in range(len(data[0])):
            lens[i][j]=len(data[i][j])
    #print lens
    return lens

def printFirstLine(line,lens,i): 
    end_flag=0   
    for k in range(len(headerL)):
        if end_flag==1:
            sys.stdout.write(' '*headerL[k])
        elif line[k]==0 :
            sys.stdout.write(' '*(lens[i][k]/2))
            sys.stdout.write('|')
            sys.stdout.write(' '*(headerL[k]-lens[i][k]/2-1))
            end_flag = 1
        elif line[k]==1:
            sys.stdout.write(' '*(lens[i][k]/2+1))
            sys.stdout.write('|')
            sys.stdout.write(' '*(headerL[k]-lens[i][k]/2-2))
        else:
            sys.stdout.write('-'*(lens[i][k]+2))
            sys.stdout.write(' '*(headerL[k]-lens[i][k]-2))
    
    sys.stdout.write(' '*(tailL[0]))
    for k in range(tailNum):
        sys.stdout.write(' '*(tailL[1]/2))
        sys.stdout.write('|')
        sys.stdout.write(' '*(tailL[1]-tailL[1]/2-1))          
    print
    return

def printSecondLine(line,lens,i):
    end_flag = 0
    for k in range(len(headerL)):
        if end_flag==1:
            sys.stdout.write(' '*headerL[k])
        elif line[k]==0 :
            sys.stdout.write('-'*(lens[i][k]/2+1))
            sys.stdout.write(' '*(headerL[k]-lens[i][k]/2-1)) 
            end_flag = 1
        elif line[k]==1:
            sys.stdout.write(' '*(lens[i][k]/2+1))
            sys.stdout.write('-'*(headerL[k]-lens[i][k]/2-1))    
        else:
            sys.stdout.write('|')
            for num in range(lens[i][k]):
                sys.stdout.write(line[k][num])
            sys.stdout.write('|')
            #if k!=len(headerL)-1:
            #    sys.stdout.write('-'*(headerL[k]-lens[i][k]-2))
            #else :
            #    sys.stdout.write(' '*(headerL[k]-lens[i][k]-2))
            sys.stdout.write('-'*(headerL[k]-lens[i][k]-2))
    
    if end_flag==1:
            sys.stdout.write(' '*headerL[k])
    else: 
        sys.stdout.write('(')     
        for num in range(len(tailData[i])):
            sys.stdout.write(tailData[i][num]) 
        sys.stdout.write(')')            
        sys.stdout.write('-'*(tailL[0]-len(tailData[i])-2))
    
    catch_flag=0
    for k in range(tailNum):
        if end_flag==0 and catch_flag==0:
            sys.stdout.write('-'*(tailL[1]/2))
            if k==tailNew[i]:
                sys.stdout.write('O')
                sys.stdout.write(' '*(tailL[1]-tailL[1]/2-1))
                catch_flag=1
            else :
                sys.stdout.write('-')
                sys.stdout.write('-'*(tailL[1]-tailL[1]/2-1))
        else:
            sys.stdout.write(' '*(tailL[1]/2))
            sys.stdout.write('|')
            sys.stdout.write(' '*(tailL[1]-tailL[1]/2-1))
        
    print    
    return

def printThirdLine(line,lens,i):    
    end_flag=0   
    for k in range(len(headerL)):
        if end_flag==1:
            sys.stdout.write(' '*headerL[k])
        elif line[k]==0 :
            sys.stdout.write(' '*headerL[k])
            end_flag=1
        elif line[k]==1:
            sys.stdout.write(' '*(lens[i][k]/2+1))
            sys.stdout.write(' ')
            sys.stdout.write(' '*(headerL[k]-lens[i][k]/2-2))
        else:
            sys.stdout.write('-'*(lens[i][k]+2))
            sys.stdout.write(' '*(headerL[k]-lens[i][k]-2))
    
    sys.stdout.write(' '*(tailL[0]))
    for k in range(tailNum):
        sys.stdout.write(' '*(tailL[1]/2))
        sys.stdout.write('|')
        sys.stdout.write(' '*(tailL[1]-tailL[1]/2-1)) 
    
    print
    return

def printGra(old_data):
    data = processData(old_data)
    lens = getLen(old_data)
    for i in range(len(data)) :
        printFirstLine(data[i],lens,i);
        printSecondLine(data[i],lens,i);
        printThirdLine(data[i],lens,i);

def getMatch(tailData,num,tailNew):
    global counter
    for i in range(num):
        if tailData[num]==tailData[i]:
            return tailNew[i]
    counter = counter+1
    return counter
    
def processTailData(tailData):
    tailNew = [0]*len(tailData)
    for num in range(len(tailData)):
        tailNew[num] = getMatch(tailData,num,tailNew);        
    return tailNew

##need set testData,headerL,tailData,tailL
#testData=[['vm1','tap1','qv1->brint','br-eth2/80'],['vm2','tap12','qv2->brint','br-eth1/10'],\
#          ['vm3','tap13','qv3->brint','br-eth1/80'],['vm4','tap14','qv4->brint','br-eth1/20'],\
#          ['vm1','tap2','qv2->brint','br-eth1/20'],['vm2','tap2','qv1->brint','br-eth1/80']]
#headerL=[8,9,15,15]
#tailData = ['net1','net1','net2','net2','net3','net1']
#tailL=[11,10]
#counter = -1# global, auto adjust, don't change
#tailNew = processTailData(tailData)
#tailNum = max(tailNew)+1
##print tailNum
##print tailNew
#printGra(testData);
def sort_data(drawData):
    sort_list=[]
    sort_drawData=[]
    for drawData_ele in drawData:
        sort_list.append(drawData_ele[4])
    new_list=list(set(sort_list))
    new_list.sort()
    for i in new_list:
        for drawData_ele in drawData:
            if drawData_ele[4]==i:
                sort_drawData.append(drawData_ele)
    return sort_drawData



if __name__ == '__main__':

    set_global_data()

    VMs = get_VM_Info()
    BRs,ETHs = get_BR_Info()
    drawData=[]
    print "----------------------------------------------------------------------------------------------------------------------------------------"
    fmt = "| %-20s | %-10s | %-5s | %-10s | %-5s | %-20s | %-10s | %-5s | %-8s | %-12s |"
    print fmt % ("VM","Status","type","Net","Vlan","MacAddress","HostName","PhyBr","IntBr","qvo/qbr/tap")
    print "----------------------------------------------------------------------------------------------------------------------------------------"
    for vm in VMs:

        if vm["status"] == "ACTIVE":
            for network in vm["network"]:
                qvo,br,host = get_qvo_id_from_BR(BRs,network["mac"])
                phybri = []
                if network["type"] == "vlan":
                    phybri = get_phybri_from_eth(ETHs,network["seg"],host)
                else:
                    phybri = get_phybri_flat(br,ETHs)
                for phybri_ele in phybri:
                    print fmt % (vm["name"],vm["status"],network["type"],network["name"],network["seg"],network["mac"],host,phybri_ele,br["name"],qvo[3:].strip("\n"))
                    drawData_ele=[]
                    drawData_ele.append(vm["name"])
                    tap="tap"+qvo[3:].strip("\n")
                    qbr="qbr"+qvo[3:].strip("\n")
                    drawData_ele.append(tap)
                    drawData_ele.append(qbr)
                    drawData_ele.append(qvo.strip("\n"))

                    phyvlanhost=phybri_ele+"/"+str(network["seg"])+"/"+host
                    drawData_ele.append(phyvlanhost)
                    drawData_ele.append(network["phynet"])
                    drawData.append(drawData_ele)

        else:
            print fmt % (vm["name"],vm["status"],network["type"],network["name"],network["seg"],network["mac"],"NA","NA","NA","NA")
    print "----------------------------------------------------------------------------------------------------------------------------------------"
    print "\n\n\n\n\n\n\n"
 #   print drawData
   # print sort_data(drawData)

    #need set testData,headerL,tailData,tailL
    testData=sort_data(drawData)
    headerL=[25,20,20,20,20]
    tailData =[]
    for ele in testData:
        tailData.append(ele[5])
    tailL=[15,15]
    counter = -1# global, auto adjust, don't change
    tailNew = processTailData(tailData)
    tailNum = max(tailNew)+1
    #print tailNum
    #print tailNew
    printGra(testData);
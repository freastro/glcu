#!/usr/bin/python
#
# glcu - gentoo linux cron update
#
# written by Michael Schilling glcu [at] 42nd (dot) de
#
# released under the GPL-2
#
# Website: http://glcu.sourceforge.net/


import sys
import os
import ConfigParser
import getopt
import output
import re
import pickle
import string
import sets
import datetime
import random


VERSION = "0.9.7.2"


fullLog = ''
rerun = ''

def exception (errMsg):
    print '\n!!! ERROR: ' + errMsg
    sys.exit(9)

def printHelp():
    print "  glcu - "+output.bold("g")+"entoo "+output.bold("l")+"inux "+output.bold("c")+"ron "+output.bold("u")+"pdate"
    print "       a program to keep your gentoo linux up to date!"
    print "       see: http://glcu.sourceforge.net/ for more information\n"
    print "                 ( Version" , VERSION , ")\n"
    print '''USAGE (for the easy update feature):
    
  glcu [-a(A)|-h|-r(R)|-v] <update-file>
      -a: run glcu in automatic mode (don't ask anything) | or not: -A
      -h: show this help message
      -r: remove prebuilt binary packages after installation | or not: -R
      -v: verbosity level (0:quiet, 1:normal, 2:verbose, 3: debugging)
      -e: command to execute after the update (e.g. -e etc-update)
      
      
  * You can adjust the complete behaviour of glcu by editing
  * the config file: /etc/glcu.conf
      
'''

    sys.exit(0)


# ask subroutine:
#   input 1. Question, 2. True or False as standard answer,
#   and optional the number of packages AND if package or glsa:
def ask(question,standardAnswer,*packageCount):
    if (standardAnswer == True):
        answerOption = ' [Y/n]'
    elif (standardAnswer == False):
        answerOption = ' [N/y]'

    print "\n " + question + answerOption 
    if (packageCount):
        what = packageCount[1]
        print "    (or you can either install only specified " + what + " number(s) #,\n     or NOT install " + what + " with -# and use i# for injecting)"
    print "\n >" ,
    extraAnswer = raw_input()
    extraAnswer.lower()
    if (extraAnswer == ''):
        return standardAnswer
    elif re.match('y',extraAnswer, re.IGNORECASE):
        standardAnswer = True
        return standardAnswer
    elif re.match('n',extraAnswer, re.IGNORECASE):
        standardAnswer = False
        return standardAnswer
    else:
        __inject = []
        __remove = []
        __install = []
        
        __answers = extraAnswer.split()
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging:  only in /etc/glcu.conf for verbosity = 3 
            print "answers: " , __answers

        for singleAnswer in __answers:
            if (re.match('i\d+',singleAnswer)):
                singleAnswer = re.sub('i','',singleAnswer,1)
                if ((int(singleAnswer) > int(packageCount[0])) or (int(singleAnswer) < 1)):
                    exception(what + " number does not exist: " + str(singleAnswer))
                __inject.append(singleAnswer)
            elif (re.match('-\d+',singleAnswer)):
                singleAnswer = re.sub('-','',singleAnswer,1)
                if ((int(singleAnswer) > int(packageCount[0])) or (int(singleAnswer) < 1)):
                    exception(what + " number does not exist: " + str(singleAnswer))
                __remove.append(singleAnswer)
            elif (re.match('\d+',singleAnswer)):
                if ((int(singleAnswer) > int(packageCount[0])) or (int(singleAnswer) < 1)):
                    exception(what + " number does not exist: " + str(singleAnswer))
                __install.append(singleAnswer)
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging:  only in /etc/glcu.conf for verbosity = 3 
            print "inject: " , __inject
            print "remove: " , __remove
            print "install: " , __install

        if ((len(__remove) > 0) and (len(__install) > 0)):
            exception("You can't specify packages to install and remove (# and -#).")

        return [__inject,__remove,__install]
    
    
class GlcuConfig:
    """
    Config Class for glcu
        1. initialize standard values
        2. read configuration file
        3. check command line options for a manual run    
    """
    
    __mainConfig = {'email':'root',
                    'verbosity':'1',
                    'update':'system',
                    'tmpdir':'/tmp',
                    'sysworldoptions':'--deep --update',
                    'cronday':'7',
                    'rerunconfig':False,
                    'updatetc':False,
                    'sync':True,
                    'eupdatedb':True,
                    'updateix':False,
                    'fixpackages':True,
                    'security':True,
                    'removeprebuilt':True,
                    'automatic':False}
    
    def __init__(self,name):
        self.name = name
        if (self.name == 'cron') or (self.name == 'manual'):
            self.__readConfigFile(self.name)
        if (self.name == 'manual'):
            self.__readCommandLineOptions()
                
                
    def getMainConfig(self,getName):
        return self.__mainConfig[getName]

    def setMainConfig(self,setName,setValue):
        __setNew = {setName:setValue}
        self.__mainConfig.update(__setNew)

    def __readConfigFile(self,runas):
        global filename
        filename = '/etc/glcu.conf'
        if (runas == 'cron' and len(sys.argv) == 2):
            if (os.path.isfile(sys.argv[1]) == 1):
                filename = sys.argv[1]
                global rerun
                rerun = random.randint(1,100)
            else:
                exception('You probably misspelled the config file in the rerunconfig option: ' + sys.argv[1])
        configFile = ConfigParser.ConfigParser()
        configFile.readfp(open(filename))
        pairs = configFile.items('default')
        for pair in pairs:
            self.setMainConfig(pair[0],pair[1])

        boolkeys = configFile.options('bool')
        for boolkey in boolkeys:
            booloption = configFile.getboolean('bool',boolkey)
            self.setMainConfig(boolkey,booloption)
            
        if (int(self.getMainConfig('verbosity')) > 2): # debugging:  only in /etc/glcu.conf for verbosity = 3 
            print "\nFrom __readConfigFile:"
            for key in self.__mainConfig.keys():
                print "  " + key + ":" , self.__mainConfig[key]
            print

        if (self.getMainConfig('rerunconfig') == filename):
            exception('rerunconfig option is set to the actual config file.\n This would cause indefinite recursion.')
    
    def __readCommandLineOptions(self):
        commandLineOptions,arguments = getopt.gnu_getopt(sys.argv[1:],'aAhrRv:e:?', ['automatic','noautomatic','help','removeprebuilt','noremoveprebuilt','verbosity=','updatetc='])
        # first check for collisions of the command line options:
        flags = []
        for checkflag in commandLineOptions:
            flags.append(checkflag[0])
        
        if (('-R' or '--noremoveprebuilt') in flags) and (('-r' or '--removeprebuilt') in flags):
            exception('Collision of commandline options: -r/-R')

        # then set the command line options:
        for clo in commandLineOptions:

            if (clo[0] == '-h') or (clo[0] == '--help') or (clo[0] == '-?'):
                printHelp()
                
            elif (clo[0] == '-A') or (clo[0] == '--noautomatic'):
                self.setMainConfig('automatic',False)
                sys.argv.remove(clo[0])
                
            elif (clo[0] == '-a') or (clo[0] == '--automatic'):
                self.setMainConfig('automatic',True)
                sys.argv.remove(clo[0])
            
            elif (clo[0] == '-R') or (clo[0] == '--noremoveprebuilt'):
                self.setMainConfig('removeprebuilt',False)
                sys.argv.remove(clo[0])
                
            elif (clo[0] == '-r') or (clo[0] == '--removeprebuilt'):
                self.setMainConfig('removeprebuilt',True)
                sys.argv.remove(clo[0])
                          
            elif (clo[0] == '-v') or (clo[0] == '--verbosity'):
                if (int(clo[1]) >= 0):
                    self.setMainConfig('verbosity',int(clo[1]))
                    sys.argv.remove(clo[0])
                    sys.argv.remove(clo[1])

            elif (clo[0] == '-e') or (clo[0] == '--updatetc'):
                self.setMainConfig('updatetc',clo[1])
                sys.argv.remove(clo[0])
                sys.argv.remove(clo[1])
                    
            

        #debugging only
        if (int(self.getMainConfig('verbosity')) > 2):
            print "\nFrom __readCommandLineOptions:"
            for key in self.__mainConfig.keys():
                print "  " + key + ":" , self.__mainConfig[key] 
            print



class ShellExecution:

    def __init__ (self,inputCommand):
        __outName = mainConfig.getMainConfig('tmpdir') + '/glcu-out.' + str(os.getpid())
        if (os.path.exists(__outName) == 1 ):
             __outName = mainConfig.getMainConfig('tmpdir') + '/glcu-out.' + str(os.getpid()) + str(random.randint(1,10000))
        self.shellCommand = inputCommand + ' >' + __outName + ' 2>&1'
        if (int(mainConfig.getMainConfig('verbosity')) > 2): #debugging
            print "shellExecution:" , ":" , self.shellCommand
        self.__oldumask = os.umask(077)
        self.__exitStatus = os.system(self.shellCommand)/256    
        
        __o = file(__outName,'r')
        self.__output = __o.read()
        __o.close()
        os.remove(__outName)
        
        
        if (int(mainConfig.getMainConfig('verbosity')) > 2): #debugging
            print "Output:" , self.__output
            print "exit status:" , self.__exitStatus
            
 

        global fullLog
        if ((int(mainConfig.getMainConfig('verbosity')) > 1) and int(self.__exitStatus) == 0):
            fullLog = fullLog + 'Log for Command: ' + self.shellCommand + "\n" + 70*"-" + "\n"
            fullLog = fullLog + self.__output
            fullLog = fullLog + 70*"=" + "\n"

    def getOutput(self):
        return self.__output
    
    def getExitStatus(self):
        return self.__exitStatus

        
        
class CronOutput:
    
    def __init__ (self):
        self.__packageSuccess = []
        self.__packageError = []
        self.__packageDependency = []
        self.__packageExists = []
        self.__packageBlocks = []
        self.__fileName = mainConfig.getMainConfig('tmpdir') + '/glcuUpdate-' + str(os.getpid()) + str(rerun)
        self.__errorLog = ''
        self.__hostname = False
        
        
        getHostname = ShellExecution('grep HOSTNAME /etc/conf.d/hostname')
        if (getHostname.getExitStatus() == 0 ):
            fileHostname = re.findall("\"(.+)\"",getHostname.getOutput())
            self.__hostname = '('  + str(fileHostname[0]) + ')'
            
    # divide packages in working and error packages
    def addPackage(self,package,status,packageOutput):
        self.package = package
        self.status = status
        
        if (self.status == 0):
            self.__packageSuccess.append(self.package)
        elif (self.status < 0):
            self.__packageDependency.append(self.package)    
        else:
            self.__packageError.append(self.package)
            self.__addErrorAppendix(self.package,packageOutput)
            
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only    
            print "AddErrorPackages:" , self.__packageError
            print "AddDependencyPackages:" , self.__packageDependency
            print "AddSuccessPackages:" , self.__packageSuccess

            
    def addExistingPackage(self,package):
        self.package = package
        self.__packageExists.append(self.package)
        

    def addBlockPackage(self,package):
        self.package = package
        self.__packageBlocks.append(self.package)
        
        
    # get full output of the log-file because there was an error during prebuilding:
    def __addErrorAppendix(self,package,output):
        self.package = package
        self.output = output
        
        self.__errorLog = self.__errorLog + "!!! Error log for " + self.package + ":\n\n" + self.output+ 70*"-" + "\n"
        
        pass
    
    
    
    def __writeTmp(self):
        # write __packageSuccess (and existing) Packages with pickle to a tmpfile 
        # if there are packages in Dep or Error add update:system/world at the beginning of the list
        
        dumpPackages = self.__packageSuccess[:]
        dumpPackages.extend(self.__packageExists[:])

        if (len(self.__packageDependency) > 0) or (len(self.__packageError) > 0):
            dumpPackages.append(mainConfig.getMainConfig('update'))
        
        tempFile = file(self.__fileName,'w')
        pickle.dump(dumpPackages,tempFile)
        tempFile.close()
        os.chmod(self.__fileName,0600)
    
    def writeMail(self):
    
        self.__writeTmp()
        # get error logs (for __packageError) and appendix if wanted
        # build eMail text and mail it

        logfilename = mainConfig.getMainConfig('tmpdir') + "/glcuLogFile-" + str(os.getpid()) + str(random.randint(1,100))
        logToFile = 0
        
        subject = 'glcu' + str(self.__hostname) + ': Updates for your Gentoo box available!'

        message = "  New Packages for 'emerge " + mainConfig.getMainConfig('update')\
        + "' available!\n  Update your Gentoo box with:\n\n          glcu "\
        + self.__fileName 
        if (len(self.__packageBlocks) > 0):
            message = message + "\n\n  You must resolve all blocks before glcu can update your system!"
        
        if (int(mainConfig.getMainConfig('verbosity')) > 1):
            if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only    
                print "Length of FullLog:" , len(fullLog)
            if ( len(fullLog) > 500000 ):
                logVar = 70*"=" + "\n\n\nFull logs:\n" +70*"=" + "\n" + fullLog
                logfile = file(logfilename,'w')
                logfile.write(logVar)
                logfile.close()
                logToFile = 1
                
        if (int(mainConfig.getMainConfig('verbosity')) > 0):
        
            message = message + "\n\n\nPrebuilding new Packages:\n" + 70*"-" + "\n"
            
            for package in self.__packageBlocks:
                message = message + string.ljust(package,57) + "BLOCK!\n"
            
            for package in self.__packageSuccess:
                message = message + string.ljust(package,57) + "success\n"
    
            for package in self.__packageExists:
                message = message + string.ljust(package,57) + "existing\n"
                
            for package in self.__packageDependency:
                message = message + string.ljust(package,57) + "dependencies*\n"
    
            for package in self.__packageError:
                message = message + string.ljust(package,57) + "ERROR**\n"
    
            message = message + 70*"-" + "\n"
            if (len(self.__packageDependency) > 0):
                message = message + "  *  Package depends on other new packages and can't be prebuild\n"
                
            if (len(self.__packageError) > 0):
                message = message + "  ** Error during prebuilding. See below for more information\n\n"
    
            if ( int(logToFile) == 1 ):
                message = message + "\n\n" + "!!! Full logs are too big to send per eMail\n!!! The logs were saved as: " + logfilename
    
            if (len(self.__errorLog) > 0):
                message = message + "\n\n\nError logs:\n" +70*"=" + "\n" + self.__errorLog 
        
        
        if ( (int(logToFile) != 1) and (int(mainConfig.getMainConfig('verbosity')) > 1) ):
            message = message + "\n\n" +70*"=" + "\n\n\nFull logs:\n" +70*"=" + "\n" + fullLog
    
        self.__eMail(subject,message)
        
    
    def earlyErrorMail(self,errorsubject,message):
        # if an early error happens (e.g. during emerge --sync or eupdatedb)
            
        subject = 'glcu' + str(self.__hostname) + ' ERROR: ' + errorsubject
        self.__eMail(subject,message)
        sys.exit(23)
    
    def __eMail(self,subject,body):
        # The core eMail function
        mailFile = mainConfig.getMainConfig('tmpdir') + '/glcuMail' + str(os.getpid()) 
        mailBody = file(mailFile,'w')
        mailBody.write(body)
        mailBody.close()
        mailcommand = '/bin/cat ' + mailFile + '|/bin/mail -s "' + subject + '" ' + mainConfig.getMainConfig('email')
        mailObject = ShellExecution(mailcommand)
        if (mailObject.getExitStatus() > 0):
            mailBody = file(mailFile,'a')
            mailBody.write('ERROR while sending eMail:\n--------------------------\n\n' + mailObject.getOutput())
            mailBody.close()
            sys.exit(100)
        else:
            os.remove(mailFile)
            
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
            print "--> sending mail to: " + mainConfig.getMainConfig('email')
        


        
def cronExecution ():
    # load configuration:
    global mainConfig
    mainConfig = GlcuConfig('cron')
    if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
        print "cronExecution: " , sys.argv

    #initialize mail object:
    mail = CronOutput()        
    
    #only run on the specified day
    myToday = datetime.date.today()
    myWeekDay = '%d' % myToday.isoweekday()    
    if ((int(mainConfig.getMainConfig('cronday')) != int(myWeekDay)) and (int(mainConfig.getMainConfig('cronday')) != 0)):
        
        if (mainConfig.getMainConfig('rerunconfig')):
            os.execv('/etc/cron.daily/glcu',['/etc/cron.daily/glcu',mainConfig.getMainConfig('rerunconfig')])
        else:
            sys.exit(0)
    
    
    
    # Check if glcu file was upated. Otherwise send mail and write check-file
    if (int(mainConfig.getMainConfig('cronday')) == 8):
        if os.path.isfile('/tmp/glcuConfigNotUpdated'):
            sys.exit(1)
        else:
            mail.earlyErrorMail('Update config file!',"Important message from glcu:\n============================\n\n  Edit the glcu config file '/etc/glcu.conf' to suit your needs!\n  Otherwise glcu won't work.")
            nO = file('/tmp/glcuConfigNotUpdated','w')
            nO.write("edit '/etc/glcu' and delete this file!")
            nO.close()
            
    # Check if there is already an glcu running
    runCheckCommand = '/bin/ps aux  | grep glcu |grep "/etc/cron" | grep -v ' + str(os.getpid())
    runCheckExitStatus = os.system(runCheckCommand)/256
    if (int(runCheckExitStatus) == 0):
        exception('There is already an instance of glcu running\n\n*** ABORTING')

        
        
            
    # 1. emerge sync

    if (mainConfig.getMainConfig('sync')):
        sync = ShellExecution('emerge --sync')
        if (sync.getExitStatus() != 0):
            mail.earlyErrorMail('emerge --sync failed','Error log for emerge --sync:\n\n' + sync.getOutput())

        
        # 2. fixpackages (if wanted and needed)
        
        if (mainConfig.getMainConfig('fixpackages')):
            if (re.search("Skipping packages. Run 'fixpackages' or set it in FEATURES",sync.getOutput())):
                fixpackages = ShellExecution('/usr/sbin/fixpackages')
                if (fixpackages.getExitStatus() != 0):
                    mail.earlyErrorMail('fixpackages failed','Error log for fixpackages:\n\n' + fixpackages.getOutput())
    

    # 3.a) run eupdatedb 

    if (mainConfig.getMainConfig('eupdatedb')):
        eupdatedb = ShellExecution('/usr/sbin/eupdatedb')
        if (eupdatedb.getExitStatus() != 0):
            mail.earlyErrorMail('eupdatedb failed','Error log for eupdatedb:\n\n' + eupdatedb.getOutput())

    # 3.b) run update-eix 

    if (mainConfig.getMainConfig('updateix')):
        eupdatedb = ShellExecution('/usr/bin/update-eix')
        if (eupdatedb.getExitStatus() != 0):
            mail.earlyErrorMail('update-eix failed','Error log for update-eix:\n\n' + eupdatedb.getOutput())
            
            
    # 4. check for security updates (if wanted)
    
    global blockList
    
    blockList = []
    updateList = []
    secPackages = []
    
    
    if (mainConfig.getMainConfig('security')):
        checkSecurity = ShellExecution('glsa-check --list --nocolor')

        if (checkSecurity.getExitStatus() != 0):
            mail.earlyErrorMail('Problem during glsa-check --list',checkSecurity.getOutput())
        secPackages = re.findall(" \[N\].*?\(\s(.*?)\s\)",checkSecurity.getOutput())
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
            print 'secPackages: ' , secPackages
        for secPackage in secPackages:
            if (re.search("\s",secPackage)):
                severalPackages = re.split("\s",secPackage)
                secPackages.remove(secPackage)
                for singlePackage in severalPackages:
                    if (singlePackage != '...'):
                        secPackages.append(singlePackage)
                if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only        
                    print 'secPackage: ' , secPackage
                    print 'severalPackages: ' , severalPackages
    
        secPackages.reverse()
        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
            print "glsa-package count: " , len(secPackages) 
            print "glsa-package list: " , secPackages

    packageList = sets.Set(secPackages)
    
    # Only prebuilt security packages if they are installed:
    newSecPList = packageList.copy()
    for package in newSecPList:
        securityCheckCommand = 'emerge --pretend ' + package + ' |grep ' + package
        securityCheck = ShellExecution(securityCheckCommand)
        if re.findall("\[ebuild\s*N",securityCheck.getOutput()):
            packageList.discard(package)
    
    # 5. check for system/world
    
    if ((mainConfig.getMainConfig('update') == 'system') or (mainConfig.getMainConfig('update') == 'world')):
        os.putenv('NOCOLOR','true')
        emergePretendCommand = 'emerge --pretend ' + mainConfig.getMainConfig('sysworldoptions') + ' ' + mainConfig.getMainConfig('update')

        emergePretend = ShellExecution(emergePretendCommand)
        if (emergePretend.getExitStatus() != 0):
            mail.earlyErrorMail('Problem during ' + emergePretendCommand,emergePretend.getOutput())
        updateList = re.findall("\[ebuild.*?\]\s(.*?)\s.*?\n",emergePretend.getOutput())
        blockList = re.findall("\[blocks.*?\]\s(.*?)\s.*?\n",emergePretend.getOutput())
        updateList.reverse()
        for block in blockList:
            mail.addBlockPackage(block)
    elif (mainConfig.getMainConfig('update') == 'security'):
        pass

    else:
        mail.earlyErrorMail('unsupported value for update-option in config file','*** ERROR***\n\n\nglcu found an unsupported option in /etc/glcu.conf:\n\n  update: ' + mainConfig.getMainConfig('update') + '\n\nThis needs to be fixed for glcu to work!')
    

    # check for duplicates (with and without version numbers):
    cpPackList = packageList.copy()
    for package in cpPackList:
        for upackage in updateList:
            rePackage = re.sub('\+','\+',package)
            if re.match(rePackage,upackage):
                packageList.discard(package)
    
    # merge set from glsa-check and list from emerge system/world
    packageList.update(updateList)
    
    if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
        print 'Number of Packages:' , len(packageList)
        print 'Packages:' , packageList
        print 'Blocking Packages:' , blockList
        
    # 6. prebuilt all needed packages (security + system/world)
    
    # check for package directory
    pkgDir = '/usr/portage/packages'
    packageDir = ShellExecution('emerge --info|grep PKGDIR')
    if (packageDir.getExitStatus() == 0):
        infoDir = re.findall("\"(.+)\"",packageDir.getOutput())
    else:
        exception('Problem during execution of: emerge --info|grep PKGDIR')
    pkgDir = infoDir[0] + '/All'
    
    # get prebuilt packages in PKGDIR:
    prebuiltPackages = []
    if (os.path.isdir(pkgDir) == 0):
        os.makedirs(pkgDir,0755)
    prebuiltDirList = os.listdir(pkgDir)
    for dirPackage in prebuiltDirList:
        prebuiltPackage = dirPackage.replace('.tbz2','')
        prebuiltPackages.append(prebuiltPackage)


    # check for already existing prebuilt Packages
    newCpPList = packageList.copy()    
    for package in newCpPList:
        # remove package paths
        prePackage = re.sub('.*/','',package)
        for prebuiltPackage in prebuiltPackages:
            rePrePackage = re.sub('\+','\+',prePackage)
            if (re.match(rePrePackage,prebuiltPackage)):
                if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                    print "Removing package:" , package
                mail.addExistingPackage(package)
                packageList.discard(package)

        
    # exit if there are no packages to update
    if (len(packageList) == 0):
        if (mainConfig.getMainConfig('rerunconfig')):
            os.execv('/etc/cron.daily/glcu',['/etc/cron.daily/glcu',mainConfig.getMainConfig('rerunconfig')])
            
        else:
            if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                print 'no packages to update. Exiting...'
            sys.exit(0)    

        
    # check for packages with dependencies (which can't be prebuild)
    depCpPList = packageList.copy()
    for depPackage in depCpPList:
        dependencyCheckCommand = 'emerge --pretend =' + depPackage
        checkDep = ShellExecution(dependencyCheckCommand)
        if (len(re.findall("\[ebuild|\[blocks",checkDep.getOutput())) != 1):
            if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                print "Removing package:" , depPackage
            mail.addPackage(depPackage,-1,checkDep.getOutput())
            packageList.discard(depPackage)
            

    # prebuilding packages        
    for package in packageList: 
        prebuildCommand = 'emerge --buildpkgonly --oneshot =' + package
        prebuild = ShellExecution(prebuildCommand)
        mail.addPackage(package,prebuild.getExitStatus(),prebuild.getOutput())


    
    # 7. save status to tmpfile for easy system update 
    #     and send eMail with report and HowTo update your system

    mail.writeMail()

    if (mainConfig.getMainConfig('rerunconfig')):
        os.execv('/etc/cron.daily/glcu',['/etc/cron.daily/glcu',mainConfig.getMainConfig('rerunconfig')])
            

    if (int(mainConfig.getMainConfig('verbosity')) > 2):
        print "\ncronExecution finished!\n\n"
    
def manualExecution ():
    # load configuration:
    global mainConfig
    mainConfig = GlcuConfig('manual')
    if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
        print "*** manualExecution: " , sys.argv[0]

    # check if glcu was started as root
    if (os.getuid() != 0):
        exception('glcu can only be run as root!')
        
    ###########################    
    # easy update if update file is given
    
    if (len(sys.argv) == 2):
        updateFilename = sys.argv.pop()
        if (os.path.isfile(updateFilename) == 1):
    
            # 1. load update file
        
            updateFile = file(updateFilename,'r')
            updates = pickle.load(updateFile)
            updateFile.close()
    
            extra = None
            global noRemove
            noRemove = True

            # 2. Check for last element (security/system/world)
            if (updates[len(updates)-1] == 'security') or (updates[len(updates)-1] == 'system') or (updates[len(updates)-1] == 'world'):
                extra = updates.pop()
                if (extra == 'security'):
                    extra = False
            rmUpdates = updates[:]
            
            print "\n" + "*"*40
            print ">> Welcome to glcu's easy update feature\n"            

            # 2.a) Check for a portage update
            for portageCheck in updates:
                if (re.match('sys-apps/portage-',portageCheck)):
                    print "\nThere is an update for portage available,\nit is recommended to update it first."
                    if (ask("Do you want to install the prebuilt portage package now?",True)):
                        updates.remove(portageCheck)
                        buildCommand = 'emerge --verbose --usepkgonly =' + portageCheck
                        buildExitStatus = os.system(buildCommand)
                    
            
            # 3. install prebuilt packages
            if (len(updates) > 0):
                if (mainConfig.getMainConfig('automatic') == False):
                    print "\n\nPrebuilt packages:\n------------------"
                    showPackages = ''
                    for uPackage in updates:
                        showPackages = showPackages + ' =' + uPackage
                    showCommand = 'emerge --pretend --verbose --usepkgonly ' + showPackages    
                    showPrebuilt = ShellExecution(showCommand)
                    if (showPrebuilt.getExitStatus() != 0):
                        exception('Problem during: ' + showCommand + '\n\n' + showPrebuilt.getOutput())
                    showLines = re.findall('\[binary.*',showPrebuilt.getOutput())
                    i = 1
                    for showLine in showLines:
                        print '(' ,
                        print "%2i" % i,
                        print ') ' + showLine
                        i = i + 1
                    answer = ask('Do you want to install the prebuilt package(s)',True,len(updates),'package')
                    if (answer == True):
                        updatePackages = ''
                        while (updates):
                            updatePackages = updatePackages + ' =' + updates.pop()
                        buildCommand = 'emerge --verbose --oneshot --usepkgonly ' + updatePackages
                        buildExitStatus = os.system(buildCommand)/256
                        if (buildExitStatus == 0):
                            noRemove = False
                    elif (answer == False):
                        pass
                    else:
                        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                            print "answer: " , answer
                        # 1. inject the wanted packages
                        if (len(answer[0]) > 0):
                            for injectPackage in answer[0]:
                                answer[1].append(injectPackage) # adding inject package to the remove list
                                injectPackage = int(injectPackage) - 1
                                # check if package was already injected
                                injectCheckCommand = 'grep ' + updates[injectPackage] + ' /etc/portage/profile/package.provided'
                                injectCheckExitStatus = os.system(injectCheckCommand)/256
                                if (int(injectCheckExitStatus) != 0):
                                    if (os.path.isdir('/etc/portage/profile') == 0):
                                        os.makedirs('/etc/portage/profile',0755)
                                    injectCommand = 'echo -e "\n' + updates[injectPackage] + '" >> /etc/portage/profile/package.provided'
                                    injectExitStatus = os.system(injectCommand)
                                else:
                                    exception('Package ' + updates[injectPackage] + ' is already injected!')
                                
                        # 2. update list of updates and install
                        if (len(answer[1]) > 0):
                            removeUpdates = sets.Set()
                            for removePackage in answer[1]:
                                removePackage = int(removePackage) - 1
                                removeUpdates.add(updates[removePackage])
                            for removeUpdate in removeUpdates:
                                updates.remove(removeUpdate)
                        
                        elif (len(answer[2]) > 0):
                            installUpdates = []
                            for installPackage in answer[2]:
                                installPackage = int(installPackage) - 1
                                installUpdates.append(updates[installPackage])
                            updates = installUpdates
                        else:
                            updates = []

                        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                            print "updates: " , updates
                        if (len(updates) > 0):
                            rmUpdates = updates[:]
                            updatePackages = ''
                            while (updates):
                                updatePackages = updatePackages + ' =' + updates.pop()
                            buildCommand = 'emerge --verbose --oneshot --usepkgonly ' + updatePackages
                            buildExitStatus = os.system(buildCommand)/256
                            if (buildExitStatus == 0):
                                noRemove = False                        
                        
                        
                else:
                    updatePackages = ''
                    while (updates):
                        updatePackages = updatePackages + ' =' + updates.pop()
                    buildCommand = 'emerge --verbose --oneshot --usepkgonly ' + updatePackages
                    buildExitStatus = os.system(buildCommand)/256
                    if (int(buildExitStatus) == 0):
                        noRemove = False
                
            # 4. ask for full install (if packages couldn't be prebuilt)    
            if (extra):
                updateCommand = 'emerge --verbose ' + mainConfig.getMainConfig('sysworldoptions') + ' ' + extra
                testExitStatus = os.system(updateCommand + ' --pretend|grep -q ebuild')/256
                if (testExitStatus == 0):
                    showExitStatus = os.system(updateCommand + ' --pretend')/256
                    if (mainConfig.getMainConfig('automatic') == False):
                        if (ask('Do you want to install above packages now?',True)):
                            extraExitStatus = os.system(updateCommand)
                            while (int(extraExitStatus) != 0):
                                if (ask("Error during emerge " + extra + ". Do you want to run 'emerge --resume --skipfirst'?",True)):
                                    extraExitStatus = os.system('emerge --resume --skipfirst')
                                else:
                                    break
##                            if (extraExitStatus == 0):
##                                noRemove == False
                    else:
                        extraExitStatus = os.system(updateCommand)
##                        if (extraExitStatus == 0):
##                            noRemove == False

            # 5. fix security
            if (mainConfig.getMainConfig('automatic') == False):
                showSecurity = ShellExecution("glsa-check --list 2>/dev/null|grep 200|grep N\]")
                if (showSecurity.getExitStatus() == 0):
                    showLines = re.findall('200.*',showSecurity.getOutput())
                    glsas = re.findall('(\d+-\d+)',showSecurity.getOutput())
                    print "glsa's: " , glsas
                    i = 1
                    for showLine in showLines:
                        print '(' ,
                        print "%2i" % i,
                        print ') ' + showLine
                        i = i + 1
                    
                    glsaAnswer = ask("Do you want to fix all glsa's now?",True,len(showLines),'glsa')
                    if (glsaAnswer == True):
                        secCommand = 'glsa-check --fix new'
                        securityExitStatus = os.system(secCommand)
                    elif (glsaAnswer == False):
                        pass
                    else:
                        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                            print "glsaAnswer: " , glsaAnswer
                        # 1. inject the wanted packages
                        if (len(glsaAnswer[0]) > 0):
                            for injectPackage in glsaAnswer[0]:
                                glsaAnswer[1].append(injectPackage)
                                injectPackage = int(injectPackage) - 1
                                injectCommand = 'glsa-check --inject ' + glsas[injectPackage] + ' 2>/dev/null'
                                injectExitStatus = os.system(injectCommand)
                                
                        # 2. update list of updates and install
                        if (len(glsaAnswer[1]) > 0):
                            removeGlsas = sets.Set()
                            for removeGlsa in glsaAnswer[1]:
                                removeGlsa = int(removeGlsa) - 1
                                removeGlsas.add(glsas[removeGlsa])
                            for removeGlsa in removeGlsas:
                                glsas.remove(removeGlsa)
                        
                        elif (len(glsaAnswer[2]) > 0):
                            installGlsas = []
                            for installGlsa in glsaAnswer[2]:
                                installGlsa = int(installGlsa) - 1
                                installGlsas.append(glsas[installGlsa])
                            glsas = installGlsas

                        else:
                            glsas = []
                            
                        if (int(mainConfig.getMainConfig('verbosity')) > 2): # debugging only
                            print "glsa's: " , glsas
                        if (len(glsas) > 0):
                            updateGlsa = ''
                            while (glsas):
                                updateGlsa = updateGlsa + ' ' + glsas.pop()
                            glsaCommand = 'glsa-check --fix' + updateGlsa
                            buildExitStatus = os.system(glsaCommand)                  
                        
                        
            else:
                secCommand = 'glsa-check --fix new'
                securityExitStatus = os.system(secCommand)
            
            # 6. remove updateFilename and binary packages if wanted:
            if (noRemove == False):
                os.remove(updateFilename)
                if mainConfig.getMainConfig('removeprebuilt'):
                    pkgDir = '/usr/portage/packages'
                    packageDir = ShellExecution('emerge --info|grep PKGDIR')
                    if (packageDir.getExitStatus() == 0):
                        infoDir = re.findall("\"(.+)\"",packageDir.getOutput())
                    else:
                        exception('Problem during execution of: emerge --info|grep PKGDIR')
                    pkgDir = infoDir[0] + '/All/'
                    for packageName in rmUpdates:
                        packageShortName = re.sub('.*/','',packageName)
                        packagePath = pkgDir + packageShortName + '*.tbz2'
                        print "removing " + packagePath
                        os.system('rm ' + packagePath)

                        packageLnkPath =  infoDir[0] + '/' + packageName + '*.tbz2'
                        print "removing " + packageLnkPath
                        os.system('rm ' + packageLnkPath) 
                        
            # 7. Ask to update the config files:
            if (mainConfig.getMainConfig('updatetc')):
                if (ask('Do you want to run ' + mainConfig.getMainConfig('updatetc') + ' now?',True)):
                    os.system(mainConfig.getMainConfig('updatetc'))
                    
                    
                    
        else:
            exception(updateFilename + ' is not a update file')

    # print help if no update file is given
    else:
        printHelp()


    


    

if re.match('/etc/cron',sys.argv[0]):
    cronExecution()
    
else:
    manualExecution()
    


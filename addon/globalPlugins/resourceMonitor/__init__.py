#Resource Monitor for NvDA
#Presents basic info on CPU load, memory and disk usage, as well as battery information.
#Authors: Alex Hall, Joseph Lee, Beqa Gozalishvili, Tuukka Ojala
# Copyright 2013-2017, released under GPL.

try:
	import winreg #Python 3
except ImportError:
	import _winreg as winreg # Python 2
from datetime import datetime
import sys
import os
import globalPluginHandler
import ui
import api
import scriptHandler
impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
# Eventually use Python 3 version by default.
# For now, Python 2 version will be used.
if sys.version.startswith("3."):
	import psutil
else:
	import psutilpy2 as psutil
del sys.path[-1]
import battery
import addonHandler
addonHandler.initTranslation()

# Styles of size calculation/string composition, do not change!
# Treditional style, Y, K, M, G, B, ...
traditional = [
	(1024.0**8.0, 'Y'),
	(1024.0**7.0, 'Z'),
	(1024.0**6.0, 'E'),
	(1024.0**5.0, 'P'),
	(1024.0**4.0, 'T'), 
	(1024.0**3.0, 'G'), 
	(1024.0**2.0, 'M'), 
	(1024.0**1.0, 'K'),
	(1024.0**0.0, 'B'),
	]

# Alternative style (displayed with most PCs): MB, KB, GB, YB, ZB, ...
alternative = [
	(1024.0**8.0, ' YB'),
	(1024.0**7.0, ' ZB'),
	(1024.0**6.0, ' EB'),
	(1024.0**5.0, ' PB'),
	(1024.0**4.0, ' TB'), 
	(1024.0**3.0, ' GB'), 
	(1024.0**2.0, ' MB'), 
	(1024.0**1.0, ' KB'),
	(1024.0**0.0, (' byte', ' bytes')),
	]

# Verbose style: Kilobytes, Megabytes, Gigabytes, ...
verbose = [
	(1024.0**8.0, ' yottabytes'),
	(1024.0**7.0, ' zettabytes'),
	(1024.0**6.0, ' exabytes'),
	(1024.0**5.0, (' petabyte', ' petabytes')),
	(1024.0**4.0, (' terabyte', ' terabytes')), 
	(1024.0**3.0, (' gigabyte', ' gigabytes')), 
	(1024.0**2.0, (' megabyte', ' megabytes')), 
	(1024.0**1.0, (' kilobyte', ' kilobytes')),
	(1024.0**0.0, (' byte', ' bytes')),
	]

# International Electrotechnical Commission (IEC) style: Ki, Mi, Gi, Ti, ...
iec = [
	(1024.0**8.0, 'Yi'),
	(1024.0**7.0, 'Zi'),
	(1024.0**6.0, 'Ei'),
	(1024.0**5.0, 'Pi'),
	(1024.0**4.0, 'Ti'),
	(1024.0**3.0, 'Gi'), 
	(1024.0**2, 'Mi'), 
	(1024.0**1.0, 'Ki'),
	(1024.0**0.0, ''),
	]

# International System of Units (Si) style: each unit is 1000 of another (i.e. 1000 KB is 1 MB)
si = [
	(1000.0**8.0, 'Y'),
	(1000.0**7.0, 'Z'),
	(1000.0**6.0, 'E'),
	(1000.0**5.0, 'P'),
	(1000.0**4.0, 'T'), 
	(1000.0**3.0, 'G'), 
	(1000.0**2.0, 'M'), 
	(1000.0**1.0, 'K'),
	(1000.0**0.0, 'B'),
	]

def size(bytes, system=traditional):
	for factor, suffix in system:
		if float(bytes) >= float(factor):
			break
	amount = float(bytes/factor)
	if isinstance(suffix, tuple):
		singular, multiple = suffix
		if float(amount) == 1.0:
			suffix = singular
		else:
			suffix = multiple
	return "{:.2F}{}".format(float(amount), suffix)

def tryTrunk(n):
	#this method basically removes decimal zeros, so 5.0 will just be 5.
	#If the number ends in anything other than a 0, nothing happens (if the trunkated number is not equal to the decimal).
	if n==int(n): return int(n)
	return n

# Record Windows Server 10 builds to release ID's.
# Client versions will be checked via Registry.
server10LTSBuilds={
	14393:"Windows Server 2016",
}

def _win10RID(buildNum, isClient):
	currentVersion = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\Microsoft\Windows NT\CurrentVersion")
	productName = winreg.QueryValueEx(currentVersion, "ProductName")[0]
	# Version 1511 and later.
	try:
		releaseID = winreg.QueryValueEx(currentVersion, "ReleaseID")[0]
	except:
		releaseID = "Unknown"
	winreg.CloseKey(currentVersion)
	# Insider Preview builds.
	if "Preview" in productName:
		return "Windows 10 Insider" if isClient else "Windows Server Insider"
	if isClient:
		if buildNum == 10240: return "Windows 10Ver1507"
		else: return "Windows 10Ver{0}".format(releaseID)
	else:
		if buildNum in server10LTSBuilds:
			return server10LTSBuilds[buildNum]
		else: return "Windows Server {0}".format(releaseID)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	# Translators: The gestures category for this add-on in input gestures dialog (2013.3 or later).
	scriptCategory = _("Resource Monitor")

	# Translators: Presented when a resource summary is copied to clipboard.
	RMCopyMessage = _("Resource summary copied to clipboard")

	def script_announceBatteryInfo(self, gesture):
		battery.getInfo()
		if battery.noBattery:
			# Translators: Message reported when there is no battery on the system, mostly laptops with battery pack removed and running on AC power.
			info=_("This computer does not have a battery connected.")
		elif not battery.onBattery: 
			# Translators: message presented when AC is connected and battery is charging, also show current battery percentage.
			info=_("{percent}%, battery charging.").format(percent=tryTrunk(battery.percentage))
		elif battery.onBattery: 
			# Translators: message presented when computer is running on battery power, showing percentage remaining and estimated remaining time.
			info=_("{percent}% battery remaining, about {time}.").format(percent=tryTrunk(battery.percentage), time=battery.timeLeft)
			if battery.low:
				# Translators: Message reported when battery level is low.
				info+=_(" Warning: low battery.")
			elif battery.critical:
				# Translators: Message reported when battery level is critical.
				info+=_(" Warning: battery is critically low.")
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(info)
		else:
			if api.copyToClip(info): ui.message(self.RMCopyMessage)
	# Translators: Input help message about battery info command in Resource Monitor.
	script_announceBatteryInfo.__doc__=_("Presents battery percentage, charging status, remaining time (if not charging), and a warning if the battery is low or critical.")

	def script_announceDriveInfo(self, gesture):
		#goes through all registered drives and gives info on each one
		info = []
		for drive in psutil.disk_partitions():
			#get info on each one
			# If and only if the Windows says disk is ready in order to avoid a core stack freeze when no disk is inserted into a slot.
			# This can be checked by looking for a file system.
			if drive.fstype:
				driveInfo=psutil.disk_usage(drive[0])
				# Translators: Shows drive letter, type of drive (fixed or removable), used capacity and total capacity of a drive (example: C drive, ntfs; 40 GB of 100 GB used (40%).
				info.append(_("{driveName} ({driveType} drive): {usedSpace} of {totalSpace} used {percent}%.").format(driveName=drive[0], driveType=drive[2], usedSpace=size(driveInfo[1], alternative), totalSpace=size(driveInfo[0], alternative), percent=tryTrunk(driveInfo[3])))
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(" ".join(info))
		else:
			if api.copyToClip(" ".join(info)): ui.message(self.RMCopyMessage)
	# Translators: Input help message about drive info command in Resource Monitor.
	script_announceDriveInfo.__doc__=_("Presents the used and total space of the static and removable drives on this computer.")

	def script_announceProcessorInfo(self, gesture):
		cores=psutil.cpu_count() #number of cores
		averageLoad=psutil.cpu_percent()
		#lists load for each core
		perCpuLoad=psutil.cpu_percent(percpu=True)
		coreLoad = []
		for i in range(len(perCpuLoad)):
			# Translators: Shows average load of CPU cores (example: core 1, 50%).
			coreLoad.append(_("Core {coreNumber}: {corePercent}%").format(coreNumber=str(i+1), corePercent=tryTrunk(perCpuLoad[i])))
		# Translators: Shows average load of the processor and the load for each core.
		info=_("Average CPU load {avgLoad}%, {cores}.").format(avgLoad=tryTrunk(averageLoad), cores=", ".join(coreLoad))
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(info)
		else:
			if api.copyToClip(info): ui.message(self.RMCopyMessage)
	# Translators: Input help mode message about processor info command in Resource Monitor.
	script_announceProcessorInfo.__doc__=_("Presents the average processor load and the load of each core.")

	def script_announceRamInfo(self, gesture):
		ram=psutil.virtual_memory()
		# Translators: Shows RAM (physical memory) usage.
		info=_("Physical: {physicalUsed} of {physicalTotal} used ({physicalPercent}%). ").format(physicalUsed=size(ram[3], alternative), physicalTotal=size(ram[0], alternative), physicalPercent=tryTrunk(ram[2]))
		virtualRam=psutil.swap_memory()
		# Translators: Shows virtual memory usage.
		info+=_("Virtual: {virtualUsed} of {virtualTotal} used ({virtualPercent}%).").format(virtualUsed=size(virtualRam[1], alternative), virtualTotal=size(virtualRam[0], alternative), virtualPercent=tryTrunk(virtualRam[3]))
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(info)
		else:
			if api.copyToClip(info): ui.message(self.RMCopyMessage)
	# Translators: Input help mode message about memory info command in Resource Monitor.
	script_announceRamInfo.__doc__=_("Presents the used and total space for both physical and virtual ram.")

	def getWinVer(self):
		# Obtain winversion. Python's Platform module provides below functionality, but platform module is not available for NVDA.
		# Prepare to receive various components for Windows info output.
		winMajor, winMinor, winverName, sp, server, is64Bit, x64 = sys.getwindowsversion().major, sys.getwindowsversion().minor, "", sys.getwindowsversion().service_pack, sys.getwindowsversion().product_type, os.environ.get("PROCESSOR_ARCHITEW6432") in ("AMD64","ARM64"), ""
		# Determine Windows version.
		if winMajor == 5: # XP (5.1) or Server 2003 (5.2).
			if winMinor == 1: winverName = "Windows XP" # Since most XP systems use 32-bit editions.
			elif winMinor == 2: winverName = "Windows Server 2003"
		elif winMajor == 6: # Vista/Server 2008 (6.0), 7/2008 R2 (6.1), 8/2012 (6.2), 8.1/2012 R2 (6.3).
			if winMinor == 0: winverName = "Windows Vista" if server == 1 else "Windows Server 2008" # Vista.
			elif winMinor == 1: winverName = "Windows 7" if server == 1 else "Windows Server 2008 R2" # Windows 7
			elif winMinor == 2: winverName = "Windows 8" if server == 1 else "Windows Server 2012" # Windows 8.
			elif winMinor == 3: winverName = "Windows 8.1" if server == 1 else "Windows Server 2012 R2" # Windows 8.1.
		elif winMajor == 10: # Windows 10/Server 2016 (10.0) and beyond.
			# Also take care of release ID, introduced in Version 1511.
			buildNum = sys.getwindowsversion().build
			currentVersion = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\Microsoft\Windows NT\CurrentVersion")
			ubr = winreg.QueryValueEx(currentVersion, "UBR")[0] #UBR = Update Build Revision
			winreg.CloseKey(currentVersion)
			winverName = _win10RID(buildNum, server == 1)
			buildRevision = ".".join([str(buildNum), str(ubr)])
		# Translators: Presented under 64-bit Windows.
		if is64Bit: x64 = _("64-bit")
		# Translators: Presented under 32-bit Windows.
		else: x64 = _("32-bit")
		# Translators: Presents Windows version (example output: "Windows version: Windows XP (32-bit)").
		if not sp: info = _("Windows version: {winVersion} ({cpuBit})").format(winVersion = winverName, cpuBit = x64)
		# Translators: Presents Windows version and service pack level (example output: "Windows version: Windows 7 service pack 1 (64-bit)").
		else: info = _("Windows version: {winVersion} {servicePackLevel} ({cpuBit})").format(winVersion = winverName, servicePackLevel = sp, cpuBit = x64)
		if (winMajor, winMinor) == (10, 0): info = info + " build {build}".format(build = buildRevision)
		return info

	def script_announceWinVer(self, gesture):
		info = self.getWinVer()
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(info)
		else:
			if api.copyToClip(info): ui.message(self.RMCopyMessage)
	# Translators: Input help mode message about Windows version command in Resource Monitor.
	script_announceWinVer.__doc__=_("Announces the version of Windows you are using.")

	def getUptime(self):
		bootTimestamp = psutil.boot_time()
		if bootTimestamp == 0.0:
			raise TypeError
		uptime = datetime.now() - datetime.fromtimestamp(bootTimestamp)
		hours, remainingMinutes = divmod(uptime.seconds, 3600)
		minutes, seconds = divmod(remainingMinutes, 60)
		hoursMinutesSeconds = "{hours:02}:{minutes:02}:{seconds:02}".format(hours=hours, minutes=minutes, seconds=seconds)
		# Translators: The system's uptime
		return _("{days} days, {hoursMinutesSeconds}").format(days=uptime.days, hoursMinutesSeconds=hoursMinutesSeconds)

	def script_announceUptime(self, gesture):
		try:
			uptime = self.getUptime()
			if scriptHandler.getLastScriptRepeatCount() == 0:
				ui.message(uptime)
			else:
				if api.copyToClip(uptime):
					ui.message(self.RMCopyMessage)
		except:
			# Translators: Obtaining uptime failed
			ui.message(_("Failed to get the system's uptime."))
	# Translators: Input help mode message about obtaining the system's uptime
	script_announceUptime.__doc__=_("Announces the system's uptime.")

	def script_announceResourceSummary(self, gesture):
		# Faster to build info on the fly rather than keep appending to a string.
		# Translators: presents the overall summary of resource usage, such as CPU load and RAM usage.
		info = [(_("{ramPercent}% RAM used, CPU at {cpuPercent}%.").format(ramPercent=tryTrunk(psutil.virtual_memory()[2]), cpuPercent=tryTrunk(psutil.cpu_percent())))]
		battery.getInfo()
		if not battery.noBattery and not battery.batteryStatusUnknown and not battery.onBatteryUnknown:
			if not battery.onBattery: info.append(_("{percent}%, battery charging.").format(percent=tryTrunk(battery.percentage)))
			elif battery.onBattery:
				#discharging battery, so provide info on it
				info.append(_("{percent}% battery remaining, about {time}.").format(percent=tryTrunk(battery.percentage), time=battery.timeLeft))
				if battery.low:
					info.append(_(" Warning: low battery."))
				elif battery.critical:
					# Translators: In addition to processor and memory usage, presented when battery is low.
					info.append(_(" Warning: critically low battery."))
		ui.message(" ".join(info))
	# Translators: Input help mode message about overall system resource info command in Resource Monitor
	script_announceResourceSummary.__doc__=_("Presents used ram, average processor load, and battery info if available.")

	__gestures={
		"KB:NVDA+shift+e":"announceResourceSummary",
		"KB:NVDA+shift+1":"announceProcessorInfo",
		"KB:NVDA+shift+2":"announceRamInfo",
		"KB:NVDA+shift+3":"announceDriveInfo",
		"KB:NVDA+shift+4":"announceBatteryInfo",
		"KB:NVDA+shift+5":"announceRamInfo",
		"KB:NVDA+shift+6":"announceWinVer",
		"kb:nvda+shift+7": "announceUptime",
	}

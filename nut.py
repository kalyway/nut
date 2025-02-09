#!/usr/bin/python3
# -*- coding: utf-8 -*-
# place this file in your CDNSP directory
# add the following line to the top of your CDNSP.py file:
# from tqdm import tqdm

import argparse
import sys
import os
import re
import pathlib
import urllib3
import json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, 'lib')

from Title import Title
import Titles
import Nsps
import CDNSP
import Fs
import Config
import requests
import Hex
import Print
import threading
import signal
import Status
import time
import colorama
import Server
import pprint
import random
import cdn.Shogun
import cdn.Superfly
try:
	import Usb
except:
	Print.error('pip3 install pyusb, required for USB coms')


				
def loadTitleWhitelist():
	global titleWhitelist
	titleWhitelist = []
	with open('conf/whitelist.txt', encoding="utf8") as f:
		for line in f.readlines():
			titleWhitelist.append(line.strip().upper())
			
def loadTitleBlacklist():
	global titleBlacklist
	titleBlacklist = []
	with open('conf/blacklist.txt', encoding="utf8") as f:
		for line in f.readlines():
			titleBlacklist.append(line.strip().upper())
			
def logMissingTitles(file):
	initTitles()
	initFiles()

	f = open(file,"w", encoding="utf-8-sig")
	
	for k,t in Titles.items():
		if t.isUpdateAvailable() and (t.isDLC or t.isUpdate or Config.download.base) and (not t.isDLC or Config.download.DLC) and (not t.isDemo or Config.download.demo) and (not t.isUpdate or Config.download.update) and (t.key or Config.download.sansTitleKey) and (len(titleWhitelist) == 0 or t.id in titleWhitelist) and t.id not in titleBlacklist:
			if not t.id or t.id == '0' * 16 or (t.isUpdate and t.lastestVersion() in [None, '0']):
				continue
			f.write((t.id or ('0'*16)) + '|' + (t.key or ('0'*32)) + '|' + (t.name or '') + "\r\n")
		
	f.close()

def logNcaDeltas(file):
	initTitles()
	initFiles()

	x = open(file,"w", encoding="utf-8-sig")
	
	for k,f in Nsps.files.items():
		try:
			t = f.title()
			if (t.isDLC or t.isUpdate or Config.download.base) and (not t.isDLC or Config.download.DLC) and (not t.isDemo or Config.download.demo) and (not t.isUpdate or Config.download.update) and (t.key or Config.download.sansTitleKey) and (len(titleWhitelist) == 0 or t.id in titleWhitelist) and t.id not in titleBlacklist:
				f.open(f.path)
				if f.hasDeltas():
					Print.info(f.path)
					x.write(f.path + "\r\n")
				f.close()
		except KeyboardInterrupt:
			raise
		except BaseException as e:
			Print.info('error: ' + str(e))
		
	x.close()
	
def updateDb(url):
	initTitles()

	Print.info("Downloading new title database " + url)
	try:
		if url == '' or not url:
			return
		if "http://" not in url and "https://" not in url:
			try:
				url = base64.b64decode(url)
			except Exception as e:
				Print.info("\nError decoding url: ", e)
				return

		r = requests.get(url)
		r.encoding = 'utf-8-sig'

		if r.status_code == 200:
			Titles.loadTitleBuffer(r.text, False)
		else:
			Print.info('Error updating database: ', repr(r))
			
	except Exception as e:
		Print.info('Error downloading:' + str(e))
		raise

global status
status = None

global scrapeThreads
scrapeThreads = 16

def scrapeThread(id, delta = True):
	size = len(Titles.titles) // scrapeThreads
	st = Status.create(size, 'Thread ' + str(id))
	for i,titleId in enumerate(Titles.titles.keys()):
		try:
			if (i - id) % scrapeThreads == 0:
				Titles.get(titleId).scrape(delta)
				st.add()
		except BaseException as e:
			Print.error(str(e))
	st.close()

global activeDownloads
activeDownloads = []

def downloadThread(i):
	Print.info('starting thread ' + str(i))
	global status
	while Config.isRunning:
		try:
			id = Titles.queue.shift()
			if id and Titles.contains(id):
				activeDownloads[i] = 1
				t = Titles.get(id)
				path = CDNSP.download_game(t.id.lower(), t.lastestVersion(), t.key, True, '', True)

				if os.path.isfile(path):
					nsp = Fs.Nsp(path, None)
					nsp.move()
					Nsps.files[nsp.path] = nsp
					Nsps.save()
					status.add()
				activeDownloads[i] = 0
			else:
				time.sleep(1)
		except KeyboardInterrupt:
			pass
		except BaseException as e:
			Print.error(str(e))
	activeDownloads[i] = 0
	Print.info('ending thread ' + str(i))

global downloadThreadsStarted
downloadThreadsStarted = False

def startDownloadThreads():
	global downloadThreadsStarted
	global activeDownloads

	if downloadThreadsStarted:
		return

	downloadThreadsStarted = True

	initTitles()
	initFiles()

	threads = []
	for i in range(Config.threads):
		activeDownloads.append(0)
		t = threading.Thread(target=downloadThread, args=[i])
		t.daemon = True
		t.start()
		threads.append(t)

def downloadAll(wait = True):
	initTitles()
	initFiles()

	global activeDownloads
	global status

	try:

		for k,t in Titles.items():
			if t.isUpdateAvailable() and (t.isDLC or t.isUpdate or Config.download.base) and (not t.isDLC or Config.download.DLC) and (not t.isDemo or Config.download.demo) and (not t.isUpdate or Config.download.update) and (t.key or Config.download.sansTitleKey) and (len(titleWhitelist) == 0 or t.id in titleWhitelist) and t.id not in titleBlacklist:
				if not t.id or t.id == '0' * 16 or (t.isUpdate and t.lastestVersion() in [None, '0']):
					#Print.warning('no valid id? ' + str(t.path))
					continue
				
				if not t.lastestVersion():
					Print.info('Could not get version for ' + str(t.name))
					continue

				Titles.queue.add(t.id)
		Titles.save()
		status = Status.create(Titles.queue.size(), 'Total Download')
		startDownloadThreads()
		while wait and (not Titles.queue.empty() or sum(activeDownloads) > 0):
			time.sleep(1)
	except KeyboardInterrupt:
		pass
	except BaseException as e:
		Print.error(str(e))

	if status:
		status.close()

def scanDLC(id, showErr = True, dlcStatus = None):
	id = id.upper()
	title = Titles.get(id)
	baseDlc = Title.baseDlcId(id)
	for i in range(0x1FF):
		scanId = format(baseDlc + i, 'X').zfill(16)
		if Titles.contains(scanId):
			continue
		ver = CDNSP.get_version(scanId.lower())
		if ver != None:
			t = Title()
			t.setId(scanId)
			Titles.set(scanId, t)
			Titles.save()
			Print.info('Found new DLC ' + str(title.name) + ' : ' + scanId)
		elif showErr:
			Print.info('nothing found at ' + scanId + ', ' + str(ver))
		if dlcStatus:
			dlcStatus.add()
	# CDNSP.get_version(args.info.lower())

def scanDLCThread(queue, dlcStatus):
	while queue.size() > 0 and Config.isRunning:
		id = queue.shift()
		if id:
			scanDLC(id, False, dlcStatus)

def startDlcScan(queue):
	dlcStatus = Status.create(queue.size() * 0x200, 'DLC Scan')
	#scanDLC(id)
	threads = []
	for i in range(scrapeThreads):
		t = threading.Thread(target=scanDLCThread, args=[queue, dlcStatus])
		t.start()
		threads.append(t)

	for t in threads:
		t.join()
	dlcStatus.close()

# 0100EBE002B3E000
def getRandomTitleId():
	n = random.randint(0, 0x10000000)
	id = 0x100000000000000
	id += (n & 0xFFFF) << 12
	id += (n & 0xFFF0000) << 20

	return format(id, 'X').zfill(16)

def scanBaseThread(baseStatus):
	while Config.isRunning:
		try:
			id = getRandomTitleId()

			if Titles.contains(id):
				continue

			ver = CDNSP.get_version(id.lower())

			if ver != None:
				Print.info('Found new base ' + id)
				t = Title()
				t.setId(id)
				Titles.set(id, t)
				Titles.save()

			baseStatus.add()
		except BaseException as e:
			print('exception: ' + str(e))

def startBaseScan():
	baseStatus = Status.create(pow(2,28), 'Base Scan')

	threads = []
	for i in range(scrapeThreads):
		t = threading.Thread(target=scanBaseThread, args=[baseStatus])
		t.start()
		threads.append(t)

	for t in threads:
		t.join()

	baseStatus.close()

			
def export(file, cols = ['id', 'rightsId', 'key', 'isUpdate', 'isDLC', 'isDemo', 'name', 'baseName', 'version', 'region']):
	initTitles()
	Titles.export(file, cols)

global hasScanned
hasScanned = False

def scan():
	global hasScanned

	if hasScanned:
		return
	hasScanned = True
	initTitles()
	initFiles()

	
	refreshRegions()
	importRegion(Config.region, Config.language)

	Nsps.scan(Config.paths.scan)
	Titles.save()
	
def organize():
	initTitles()
	initFiles()

	#scan()
	Print.info('organizing')
	for k, f in Nsps.files.items():
		#print('moving ' + f.path)
		#Print.info(str(f.hasValidTicket) +' = ' + f.path)
		f.move()
	Print.info('removing empty directories')
	Nsps.removeEmptyDir('.', False)
	Nsps.save()
		
def refresh():
	initTitles()
	initFiles()

	for k, f in Nsps.files.items():
		try:
			f.open()
			f.readMeta()
			f.close()
		except:
			raise
			pass
	Titles.save()
	
def scanLatestTitleUpdates():
	initTitles()
	initFiles()

	for k,i in CDNSP.get_versionUpdates().items():
		id = str(k).upper()
		version = str(i)
		
		if not Titles.contains(id):
			if len(id) != 16:
				Print.info('invalid title id: ' + id)
				continue
			continue
			t = Title()
			t.setId(id)
			Titles.set(id, t)
			Print.info('Found new title id: ' + str(id))
			
		t = Titles.get(id)
		if str(t.version) != str(version):
			Print.info('new version detected for %s[%s] v%s' % (t.name or '', t.id or ('0' * 16), str(version)))
			t.setVersion(version, True)
			
	Titles.save()
	
def updateVersions(force = True):
	initTitles()
	initFiles()

	i = 0
	for k,t in Titles.items():
		if force or t.version == None:
			if (t.isDLC or t.isUpdate or Config.download.base) and (not t.isDLC or Config.download.DLC) and (not t.isDemo or Config.download.demo) and (not t.isUpdate or Config.download.update) and (t.key or Config.download.sansTitleKey) and (len(titleWhitelist) == 0 or t.id in titleWhitelist) and t.id not in titleBlacklist:
				v = t.lastestVersion(True)
				Print.info("%s[%s] v = %s" % (str(t.name), str(t.id), str(v)) )
			
				i = i + 1
				if i % 20 == 0:
					Titles.save()
			
	for t in list(Titles.data().values()):
		if not t.isUpdate and not t.isDLC and t.updateId and t.updateId and not Titles.contains(t.updateId):
			u = Title()
			u.setId(t.updateId)
			
			if u.lastestVersion():
				Titles.set(t.updateId, u)
				
				Print.info("%s[%s] FOUND" % (str(t.name), str(u.id)) )
				
				i = i + 1
				if i % 20 == 0:
					Titles.save()
					
	Titles.save()

isInitTitles = False

def initTitles():
	global isInitTitles
	if isInitTitles:
		return

	isInitTitles = True

	Titles.load()

	loadTitleWhitelist()
	loadTitleBlacklist()

	Nsps.load()
	Titles.queue.load()

isInitFiles = False
def initFiles():
	global isInitFiles
	if isInitFiles:
		return

	isInitFiles = True

	Nsps.load()

def unlockAll():
	initTitles()
	initFiles()

	for k,f in Nsps.files.items():
		if f.isUnlockable():
			try:
				Print.info('unlocking ' + f.path)
				f.open(f.path, 'r+b')
				f.unlock()
				f.close()
			except BaseException as e:
				Print.info('error unlocking: ' + str(e))

def submitKeys():
	try:
		import blockchain
	except:
		raise
	for id, t in Titles.items():
		if t.key: #and not t.isUpdate:
			try:
				blockchain.blockchain.suggest(t.id, t.key)
			except LookupError as e:
				Print.info(str(e))
			except OSError as e:
				Print.info(str(e))
			except BaseException as e:
				Print.info(str(e))
				raise

def refreshRegions():
	for region in Config.regionLanguages():
		for language in Config.regionLanguages()[region]:
			for i in Titles.data(region, language):
				regionTitle = Titles.data(region, language)[i]

				if regionTitle.id:
					title = Titles.get(regionTitle.id, None, None)

					if not hasattr(title, 'regions') or not title.regions:
						title.regions = []

					if not hasattr(title, 'languages') or not title.languages:
						title.languages = []

					if not region in title.regions:
						title.regions.append(region)

					if not language in title.languages:
						title.languages.append(language)
	Titles.save()

def importRegion(region = 'US', language = 'en'):
	if not region in Config.regionLanguages() or language not in Config.regionLanguages()[region]:
		Print.error('Could not locate %s/%s !' % (region, language))
		return False

	for region2 in Config.regionLanguages():
		for language2 in Config.regionLanguages()[region2]:
			for nsuId, regionTitle in Titles.data(region2, language2).items():
				if not regionTitle.id:
					continue
				title = Titles.get(regionTitle.id, None, None)
				title.importFrom(regionTitle, region2, language2)

	for region2 in Config.regionLanguages():
		for language2 in Config.regionLanguages()[region2]:
			if language2 != language:
				continue
			for nsuId, regionTitle in Titles.data(region2, language2).items():
				if not regionTitle.id:
					continue
				title = Titles.get(regionTitle.id, None, None)
				title.importFrom(regionTitle, region2, language2)


	for nsuId, regionTitle in Titles.data(region, language).items():
		if not regionTitle.id:
			continue

		title = Titles.get(regionTitle.id, None, None)
		title.importFrom(regionTitle, region, language)

	Titles.save()

			
if __name__ == '__main__':
	try:
		titleWhitelist = []
		titleBlacklist = []

		urllib3.disable_warnings()

		#signal.signal(signal.SIGINT, handler)


		CDNSP.tqdmProgBar = False


		CDNSP.hactoolPath = Config.paths.hactool
		CDNSP.keysPath = Config.paths.keys
		CDNSP.NXclientPath = Config.paths.NXclientCert
		CDNSP.ShopNPath = Config.paths.shopNCert
		CDNSP.reg = Config.cdn.region
		CDNSP.fw = Config.cdn.firmware
		CDNSP.deviceId = Config.cdn.deviceId
		CDNSP.env = Config.cdn.environment
		CDNSP.dbURL = 'titles.txt'
		CDNSP.nspout = Config.paths.nspOut


		if CDNSP.keysPath != '':
			CDNSP.keysArg = ' -k "%s"' % CDNSP.keysPath
		else:
			CDNSP.keysArg = ''


		parser = argparse.ArgumentParser()
		parser.add_argument('file',nargs='*')
		parser.add_argument('--base', type=int, choices=[0, 1], default=Config.download.base*1, help='download base titles')
		parser.add_argument('--demo', type=int, choices=[0, 1], default=Config.download.demo*1, help='download demo titles')
		parser.add_argument('--update', type=int, choices=[0, 1], default=Config.download.update*1, help='download title updates')
		parser.add_argument('--dlc', type=int, choices=[0, 1], default=Config.download.DLC*1, help='download DLC titles')
		parser.add_argument('--nsx', type=int, choices=[0, 1], default=Config.download.sansTitleKey*1, help='download titles without the title key')
		parser.add_argument('-D', '--download-all', action="store_true", help='download ALL title(s)')
		parser.add_argument('-d', '--download', nargs='+', help='download title(s)')
		parser.add_argument('-i', '--info', help='show info about title or file')
		parser.add_argument('--depth', type=int, default=1, help='max depth for file info and extraction')
		parser.add_argument('-I', '--verify', help='verify title key')
		parser.add_argument('-u', '--unlock', help='install available title key into NSX / NSP')
		parser.add_argument('--unlock-all', action="store_true", help='install available title keys into all NSX files')
		parser.add_argument('--set-masterkey1', help='Changes the master key encryption for NSP.')
		parser.add_argument('--set-masterkey2', help='Changes the master key encryption for NSP.')
		parser.add_argument('--set-masterkey3', help='Changes the master key encryption for NSP.')
		parser.add_argument('--set-masterkey4', help='Changes the master key encryption for NSP.')
		parser.add_argument('--set-masterkey5', help='Changes the master key encryption for NSP.')
		parser.add_argument('--remove-title-rights', nargs='+', help='Removes title rights encryption from all NCA\'s in the NSP.')
		parser.add_argument('-s', '--scan', action="store_true", help='scan for new NSP files')
		parser.add_argument('-Z', action="store_true", help='update ALL title versions from nintendo')
		parser.add_argument('-z', action="store_true", help='update newest title versions from nintendo')
		parser.add_argument('-V', action="store_true", help='scan latest title updates from nintendo')
		parser.add_argument('-o', '--organize', action="store_true", help='rename and move all NSP files')
		parser.add_argument('-U', '--update-titles', action="store_true", help='update titles db from urls')
		parser.add_argument('-r', '--refresh', action="store_true", help='reads all meta from NSP files and queries CDN for latest version information')
		parser.add_argument('-x', '--extract', nargs='+', help='extract / unpack a NSP')
		parser.add_argument('-c', '--create', help='create / pack a NSP')
		parser.add_argument('--export', help='export title database in csv format')
		parser.add_argument('--export-versions', help='export title version database in csv format')
		parser.add_argument('-M', '--missing', help='export title database of titles you have not downloaded in csv format')
		parser.add_argument('--nca-deltas', help='export list of NSPs containing delta updates')
		parser.add_argument('--silent', action="store_true", help='Suppress stdout/stderr output')
		parser.add_argument('--json', action="store_true", help='JSON output')
		parser.add_argument('--usb', action="store_true", help='Run usb daemon')
		parser.add_argument('-S', '--server', action="store_true", help='Run server daemon')
		parser.add_argument('-m', '--hostname', help='Set server hostname')
		parser.add_argument('-p', '--port', type=int, help='Set server port')
		parser.add_argument('-b', '--blockchain', action="store_true", help='run blockchain server')
		parser.add_argument('-k', '--submit-keys', action="store_true", help='Submit all title keys to blockchain')

		parser.add_argument('--scrape', action="store_true", help='Scrape ALL titles from Nintendo servers')
		parser.add_argument('--scrape-delta', action="store_true", help='Scrape ALL titles from Nintendo servers that have not been scraped yet')
		parser.add_argument('--scrape-title', help='Scrape title from Nintendo servers')

		parser.add_argument('--scrape-shogun', action="store_true", help='Scrape ALL titles from shogun')
		parser.add_argument('--scrape-languages', action="store_true", help='Scrape languages from shogun')

		parser.add_argument('--refresh-regions', action="store_true", help='Refreshes the region and language mappings in Nut\'s DB')
		parser.add_argument('--import-region', help='Localizes Nut\'s DB to the specified region')
		parser.add_argument('--language', help='Specify language to be used with region')

		parser.add_argument('--scan-base', nargs='*', help='Scan for new base Title ID\'s')
		parser.add_argument('--scan-dlc', nargs='*', help='Scan for new DLC Title ID\'s')

		
		args = parser.parse_args()

		Config.download.base = bool(args.base)
		Config.download.DLC = bool(args.dlc)
		Config.download.demo = bool(args.demo)
		Config.download.sansTitleKey = bool(args.nsx)
		Config.download.update = bool(args.update)

		if args.hostname:
			args.server = True
			Config.server.hostname = args.hostname

		if args.port:
			args.server = True
			Config.server.port = int(args.port)

		if args.silent:
			Print.silent = True

		if args.json:
			Config.jsonOutput = True

		Status.start()


		Print.info('                        ,;:;;,')
		Print.info('                       ;;;;;')
		Print.info('               .=\',    ;:;;:,')
		Print.info('              /_\', "=. \';:;:;')
		Print.info('              @=:__,  \,;:;:\'')
		Print.info('                _(\.=  ;:;;\'')
		Print.info('               `"_(  _/="`')
		Print.info('                `"\'')

		if args.extract:
			for filePath in args.extract:
				#f = Fs.Nsp(filePath, 'rb')
				f = Fs.factory(filePath)
				f.open(filePath, 'rb')
				dir = os.path.splitext(os.path.basename(filePath))[0]
				f.unpack(dir)
				f.close()

		if args.create:
			Print.info('creating ' + args.create)
			nsp = Fs.Nsp(None, None)
			nsp.path = args.create
			nsp.pack(args.file)
			#for filePath in args.file:
			#	Print.info(filePath)

	
		if args.update_titles:
			initTitles()
			for url in Config.titleUrls:
				updateDb(url)
			Titles.loadTxtDatabases()
			Titles.save()

		if args.submit_keys:
			initTitles()
			initFiles()
			submitKeys()

		if args.scrape_languages:
			cdn.Shogun.saveLanguages()
			exit(0)

		if args.refresh_regions:
			refreshRegions()
			exit(0)

		if args.import_region:
			region = args.import_region.upper()
			if not args.language:
				args.language = Config.language

			args.language = args.language.lower()

			importRegion(region, args.language)
			exit(0)

		if args.usb:
			scan()
			Usb.daemon()
		
		if args.download:
			initTitles()
			initFiles()
			for download in args.download:
				bits = download.split(',')

				version = None
				key = None

				if len(bits) == 1:
					id = bits[0].upper()
				elif len(bits) == 2:
					id = bits[0].upper()
					key = bits[1].strip()
				elif len(bits) == 3:
					id = bits[0].upper()
					key = bits[1].strip()
					version = bits[2].strip()
				else:
					Print.info('invalid args: ' + download)
					continue

				if key == '':
					key = None

				if version == '':
					version = None

				if len(id) != 16:
					raise IOError('Invalid title id format')

				if Titles.contains(id):
					title = Titles.get(id)

					CDNSP.download_game(title.id.lower(), version or title.lastestVersion(), key or title.key, True, '', True)
				else:
					CDNSP.download_game(id.lower(), version or Title.getCdnVersion(id.lower()), key, True, '', True)
	
		if args.scan:
			initTitles()
			initFiles()
			scan()
		
		if args.refresh:
			initTitles()
			initFiles()
			refresh()
	
		if args.organize:
			initTitles()
			initFiles()
			organize()

		if args.set_masterkey1:
			f = Fs.Nsp(args.set_masterkey1, 'r+b')
			f.setMasterKeyRev(0)
			f.flush()
			f.close()
			pass

		if args.set_masterkey2:
			f = Fs.Nsp(args.set_masterkey2, 'r+b')
			f.setMasterKeyRev(2)
			f.flush()
			f.close()
			pass

		if args.set_masterkey3:
			f = Fs.Nsp(args.set_masterkey3, 'r+b')
			f.setMasterKeyRev(3)
			f.flush()
			f.close()
			pass

		if args.set_masterkey4:
			f = Fs.Nsp(args.set_masterkey4, 'r+b')
			f.setMasterKeyRev(4)
			f.flush()
			f.close()
			pass

		if args.set_masterkey5:
			f = Fs.Nsp(args.set_masterkey5, 'r+b')
			f.setMasterKeyRev(5)
			f.flush()
			f.close()
			pass

		if args.remove_title_rights:
			initTitles()
			initFiles()
			for fileName in args.remove_title_rights:
				try:
					f = Fs.Nsp(fileName, 'r+b')
					f.removeTitleRights()
					f.flush()
					f.close()
				except BaseException as e:
					Print.error('Exception: ' + str(e))

		if args.nca_deltas:
			logNcaDeltas(args.nca_deltas)

		if args.verify:
			for fileName in args.file:
				f = Fs.factory(fileName)
				f.open(fileName, 'r+b')
				if f.verifyKey(args.verify):
					print('key verified for ' + fileName)
				else:
					print('key failure for ' + fileName)

		if args.info:
			initTitles()
			initFiles()
			print(str(len(args.info)))
			if re.search(r'^[A-Fa-f0-9]+$', args.info.strip(), re.I | re.M | re.S):
				Print.info('%s version = %s' % (args.info.upper(), CDNSP.get_version(args.info.lower())))
			else:
				f = Fs.factory(args.info)
				f.open(args.info, 'r+b')
				f.printInfo(args.depth+1)
				'''
				for i in f.cnmt():
					for j in i:
						Print.info(j._path)
						j.rewind()
						buf = j.read()
						Hex.dump(buf)
						j.seek(0x28)
						#j.writeInt64(0)
						Print.info('min: ' + str(j.readInt64()))
				#f.flush()
				#f.close()
				'''

		if args.scrape_shogun:
			initTitles()
			initFiles()

			for region in cdn.regions():
				pass
				'''
				r = cdn.Shogun.country(region)
				if not r:
					print('could not get region ' + region)
				else:
					print(str(r['default_language_code']))
				'''
				
				cdn.Shogun.scrapeTitles(region)
			Titles.saveAll()
			#cdn.Shogun.ids('01005EE0036ED001,01005EE0036ED002', 'aoc')
			#for i in cdn.Superfly.getAddOns('01005ee0036ec000'.upper()):
			#	print(str(i))
			#cdn.Shogun.scrapeLangTitles('US', 'en')

		if args.scrape_title:
			initTitles()
			initFiles()

			if not Titles.contains(args.scrape_title):
				Print.error('Could not find title ' + args.scrape_title)
			else:
				Titles.get(args.scrape_title).scrape(False)
				Titles.save()
				#Print.info(repr(Titles.get(args.scrape_title).__dict__))
				pprint.pprint(Titles.get(args.scrape_title).__dict__)

		if args.scrape or args.scrape_delta:
			initTitles()
			initFiles()

			threads = []
			for i in range(scrapeThreads):
				t = threading.Thread(target=scrapeThread, args=[i, args.scrape_delta])
				t.start()
				threads.append(t)

			for t in threads:
				t.join()
		
			Titles.save()
			
	
		if args.Z:
			updateVersions(True)
		
		if args.z:
			updateVersions(False)
		
		if args.V:
			scanLatestTitleUpdates()

		if args.unlock_all:
			unlockAll()
			pass

		if args.unlock:
			initTitles()
			initFiles()
			Print.info('opening ' + args.unlock)
			f = Fs.Nsp(args.unlock, 'r+b')
			f.unlock()
			#Print.info(hex(int(f.titleId, 16)))
			#f.ticket().setTitleKeyBlock(0x3F4E5ADCAECFB0A25C9FCABD37E68ECE)
			#f.ticket().flush()
			#Print.info(hex(f.ticket().getTitleKeyBlock()))
			#Print.info(hex(f.ticket().getTitleKeyBlock()))
			#f.close()


		
		if args.download_all:
			downloadAll()
		
		if args.export:
			initTitles()
			initFiles()
			export(args.export)

		if args.export_versions:
			initTitles()
			initFiles()
			export(args.export_versions, ['id', 'version'])
		
		if args.missing:
			logMissingTitles(args.missing)

		if args.server:
			startDownloadThreads()
			initTitles()
			initFiles()
			Server.run()

		if args.blockchain:
			initTitles()
			initFiles()
			try:
				import blockchain
			except:
				pass
			blockchain.run()
		
		if len(sys.argv)==1:
			scan()
			organize()
			downloadAll()

		if args.scan_dlc != None:
			initTitles()
			initFiles()
			queue = Titles.Queue()
			if len(args.scan_dlc) > 0:
				for id in args.scan_dlc:
					queue.add(id)
			else:
				for i,k in Titles.items():
					if not k.isDLC and not k.isUpdate and k.id:
						queue.add(k.id)
			startDlcScan(queue)

		if args.scan_base != None:
			initTitles()
			initFiles()
			startBaseScan()

		Status.close()
	

	except KeyboardInterrupt:
		Config.isRunning = False
		Status.close()
	except BaseException as e:
		Config.isRunning = False
		Status.close()
		raise

	Print.info('fin')


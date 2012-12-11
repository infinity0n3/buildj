import yaml
import re
import fnmatch

WAF_TOOLS = {'cc':   'compiler_cc',
             'c++':  'compiler_cxx',
             'vala': 'compiler_cc vala'}

# (Tool,Type) -> Waf features map
FEATURES_MAP = {('cc', 'program'):     'c cprogram',
                ('cc', 'sharedlib'):   'c cshlib',
                ('cc', 'staticlib'):   'c cstlib',
                ('c++', 'program'):    'cxx cprogram',
                ('c++', 'sharedlib'):  'cxxshlib',
                ('c++', 'staticlib'):  'cxxstlib',
                ('vala', 'program'):   'c cprogram',
                ('vala', 'sharedlib'): 'c cshlib',
                ('vala', 'staticlib'): 'c cstlib'}

CC_TOOLCHAIN = {'ADDR2LINE': 'addr2line',
                'AS': 'as', 'CC': 'gcc', 'CPP': 'cpp',
                'CPPFILT': 'c++filt', 'CXX': 'g++',
                'DLLTOOL': 'dlltool', 'DLLWRAP': 'dllwrap',
                'GCOV': 'gcov', 'LD': 'ld', 'NM': 'nm',
                'OBJCOPY': 'objcopy', 'OBJDUMP': 'objdump',
                'READELF': 'readelf', 'SIZE': 'size',
                'STRINGS': 'strings', 'WINDRES': 'windres',
                'AR': 'ar', 'RANLIB': 'ranlib', 'STRIP': 'strip'}

DEFAULT_BUILDJ_FILE="project.yaml"

class Stack(list):
	def push(self, item):
		self.append(item)
	
	def peek(self):
		if len(self):
			return self[-1]
		return
	
	def set(self, item):
		if len(self):
			self[-1] = item
		else:
			self.push(item)
	
	def is_empty(self):
		return (self == [])

def resolve_value(name, env={}):
	if name[0:2] == '${':
		print name[2:-1]
	elif name[0:2] == '$(':
		print name[2:-1]
		
	if name in env:
		return env[name]
	else:
		return name

def preprocess(data, env):
	stack = Stack()
	skip = Stack()
	ltrunk = 0
	newdata = ''
	lines = data.split('\n')
	
	for line in lines:
		line = line.rstrip()
		tmp = line.lstrip()
		ident = len(line) - len(tmp)
		
		sti = stack.peek()
		if sti:
			if ident < sti["ident"]:
				sti = stack.pop()
				if not skip.is_empty():
					skip.pop()
		# match lines starting with @
		match = re.match("(([ \t]+@)|(@))[{}A-Za-z-:*?]*", line)
		if match:
			params = re.split(':|@',line)
			
			# fix splitting of {attr:name}
			fixedparams = []
			merge = False
			item = ""
			for p in params:
				if p:
					if p[0:1] == '${':
						merge = True
						item = ""
						if p[-1] != '}':
							p += ':'
					elif p[-1] == '}':
						merge = False
						p = item + p
						
					if merge:
						item += p
					else:
						fixedparams.append(p)
			params = fixedparams
			
			doskip = False
			
			if sti and sti["ident"] < ident:
				doskip = skip.peek()
			elif sti and sti["ident"] == ident:			
				if not skip.is_empty():
					skip.pop()
	
			if not doskip:
				sti = stack.peek()
				if sti:
					if len(params[0]) > sti["ident"]:
						sti = {"var":params[1], "ident":len(params[0]), "cond":False, "preppend":sti["preppend"]}
						stack.push( sti )
						skip.push(True)
					elif len(params[0]) == sti["ident"] and params[1] != sti["var"] and params[1] != "default":
						sti = stack.pop()
						skip.set(False)
						sti = {"var":params[1], "ident":len(params[0]), "cond":False, "preppend":sti["preppend"]}
						stack.push(sti)
				else:
					sti = {"var":params[1], "ident":len(params[0]), "cond":False, "preppend":params[0]}
					stack.push( sti )
				
				if not params[1] == "default":
					if not sti["cond"]:
						if params[1] in env:
							# evaluate expression, for now, just glob patterns
							match = fnmatch.fnmatch(env[params[1]], params[2])
						else:
							match = False
						if match:
							sti["cond"] = True
							skip.set(False)
						else:
							skip.push(True)
					else:
						skip.set(True)
				else:
					if sti["cond"]:
						skip.push(True)
					else:
						skip.push(False)
		else:
			if (not skip.peek()) or skip.is_empty():
				sti = stack.peek()
				if sti:
					newdata += '{0}{1}'.format( sti["preppend"], line.lstrip() )
					newdata += '\n'
				else:
					newdata += line
					newdata += '\n'
	return newdata


def normalize_package_name (name):
	name = name.upper ()
	nonalpha = re.compile (r'\W')
	return nonalpha.sub ('_', name)

class ProjectFile:
	def __init__ (self, project=DEFAULT_BUILDJ_FILE, env={}):
		prj = open(project)
		data = prj.read ()
		# preprocess data
		data = preprocess(data, env )
		self._project = yaml.load (data)
		prj.close ()
		
		self._env = env
		
		#TODO: try to raise some meaningful (and consistent) error
		self._project_name = self._project['project']['name']
		self._project_version = self._project['project']['version']

		self._targets = []
		for target_name, target_data in self._project['targets'].iteritems():
			self._targets.append(ProjectTarget(target_name, target_data))

		for subdir in self._project.get ('subdirs', []):
			prj = open ('%s/%s' % (subdir, project))
			data = prj.read ()
			# preprocess data
			data = preprocess(data, env )
			#print data
			subproject = yaml.load (data)
			for target_name, target_data in subproject['targets'].iteritems():
				assert target_name not in self._project['targets']
				if 'path' in target_data:
					path = '%s/%s' % (subdir, target_data['path'])
				else:
					path = subdir
				target_data['path'] = path
				self._project['targets'][target_name] = target_data
				self._targets.append(ProjectTarget(target_name, target_data))

	def __repr__ (self):
		enc = json.encoder.JSONEncoder ()
		return enc.encode (self._project)

	def get_project_version (self):
		return self._project_version
		
	def get_project_name (self):
		return self._project_name
		
	def get_options (self):
		project = self._project
		if not "options" in project:
			return []

		option_list = []
		for option_name in project["options"]:
			option_list.append (ProjectOption (str(option_name), project["options"][option_name]))
		return option_list

	def get_targets (self):
		names = dict([(tgt.get_name(), tgt) for tgt in self._targets])
		deps = dict([(tgt.get_name(), tgt.get_uses()) for tgt in self._targets])
		S = [tgt for tgt in deps if not deps[tgt]]
		targets = []
		while S:
			n = S.pop(0)
			targets.append(names[n])
			for m in deps:
				if n in deps[m]:
					deps[m].remove(n)
					if not deps[m]:
						S.insert(0,m)
		return targets

	def get_tools (self):
		tools = []

		for target in self._targets:
			tool = target.get_tool ()
			if tool and tool != "data":
				tools.append (tool)
		return tools

	def get_requires (self):
		project = self._project
		if not "requires" in project:
			return
		
		return [ProjectRequirement(require, self._env, project["requires"][require])
							for require in project["requires"]]
		
	def get_packages_required (self):
		"List of pkg-config packages required"
		requires = self.get_requires ()
		return [require for require in requires if require.get_type () == "package"]
								
	def get_programs_required (self):
		"List of pkg-config packages required"
		requires = self.get_requires ()
		return [require for require in requires if require.get_type () == "program"]
											
	def get_libraries_required (self):
		"List of pkg-config packages required"
		requires = self.get_requires ()
		return [require for require in requires if require.get_type () == "library"]
		
	def get_functions_required (self):
		"List of pkg-config packages required"
		requires = self.get_requires ()
		return [require for require in requires if require.get_type () == "function"]
											
	def replace_options (self, *args):
		pass
	

class ProjectTarget(object):
	def __new__(cls, name, target):
		if not isinstance (target, dict):
			raise ValueError, "Target %s: the target argument must be a dictionary" % name

		if 'tool' in target:
			cls = TOOL_CLASS_MAP[target['tool']]
		else:
			sources = target['input']
			tools = set ()
			for src in sources:
				for tool, exts in EXT_TOOL_MAP.iteritems ():
					if any([src.endswith (ext) for ext in exts]):
						tools.add (tool)
			tools = tuple(sorted(tools))

			if len(tools) == 1:
				tool = tools[0]
			elif tools in MULTI_TOOL_MAP:
				tool = MULTI_TOOL_MAP[tools]
			else:
				raise NotImplementedError, "Target %s: you need to specify a tool"

			target['tool'] = tool
			cls = TOOL_CLASS_MAP[tool]

		return object.__new__(cls)

	def __init__(self, name, target):
		self._name	 = name
		self._target = target

	def get_name (self):
		return str(self._name)

	def get_tool (self):
		if "tool" not in self._target:
			return None
		return str(self._target["tool"])
	
	def get_type (self):
		if "type" not in self._target:
			return
		return str(self._target["type"])

	def get_path (self):
		return str(self._target.get ("path", ""))
		
	def get_features (self):
		tool = self.get_tool ()
		output_type = self.get_type ()
		if not tool or not output_type:
			#TODO: Report tool and target type needed
			return
			
		if (tool, output_type) in FEATURES_MAP:
			return FEATURES_MAP[(tool, output_type)]
		else:
			#TODO: Report lack of support for this combination
			return
	
	def _get_string_list (self, key):
		if key not in self._target:
			return []
		target_input = self._target[key]
		
		if isinstance (target_input, unicode):
			return [str(target_input),]
		elif isinstance (target_input, list):
			#TODO: Check if everything is str
			return [str(t) for t in target_input]
		else:
			return [str(target_input)]

		#TODO: Report warning, empty input
		#return []
		
	def get_input (self):
		return self._get_string_list ("input")
		
	def get_uses (self):
		return self._get_string_list ("uses")
	
	def get_version (self):
		if "version" not in self._target:
			return None
		return str(self._target["version"])
		
	def get_packages (self):
		return self._get_string_list ("packages")
			
	def get_libraries (self):
		return self._get_string_list ("libraries")			
			
	def get_vapi_dirs (self):
		return self._get_string_list ("vapidirs")
		
	def get_defines (self):
		return self._get_string_list ("defines")
	
	def get_cflags (self):
		return self._get_string_list("cflags")
	
	def get_cxxflags (self):
		return self._get_string_list("cxxflags")
	
	def get_cppflags (self):
		return self._get_string_list("cppflags")
	
	def get_linkflags (self):
		return self._get_string_list("linkflags")
	
	def get_build_arguments (self):
		"WAF bld arguments dictionary"
		args = {"features": self.get_features (),
				"source":	self.get_input (),
				"target":	self.get_name ()}
		
		return args

	def get_install_files (self):
		return

	def get_install_path (self):
		return

class CcTarget (ProjectTarget):
	def get_build_arguments (self):
		args = ProjectTarget.get_build_arguments (self)

		uses = self.get_uses ()
		if uses:
			# waf vala support will modify the list if we pass one
			args["use"] = " ".join (uses)

		if self.get_type () == "sharedlib" and self.get_version ():
			args["vnum"] = self.get_version ()

		args["uselib"] = []
		for pkg in self.get_packages ():
			args["uselib"].append (normalize_package_name(pkg))
		
		args["lib"] = []
		for lib in self.get_libraries ():
			args["lib"].append (lib)								
								
		defines = self.get_defines ()
		if defines:
			args["defines"] = defines

		args["cflags"] = []
		cflags = self.get_cflags()
		if cflags:
			args["cflags"] = cflags
		
		args["cxxflags"] = []
		cxxflags = self.get_cxxflags()
		if cxxflags:
			args["cxxflags"] = cxxflags

		args["cppflags"] = []
		cppflags = self.get_cppflags()
		if cppflags:
			args["cppflags"] = cppflags

		if self.get_type () in ("sharedlib", "staticlib"):
			args["export_includes"] = '.'
				
		return args

class ValaTarget (CcTarget):
	def get_vapi (self):
		if "vapi" in self._target:
			return str (self._target["vapi"])
		
	def get_gir (self):
		if "gir" in self._target:	
			gir = str(self._target["gir"])
			
			match = re.match (".*-.*", gir)
			if match:
				return gir
				
		return None

	def get_build_arguments (self):
		"WAF bld arguments dictionary"
		args = CcTarget.get_build_arguments (self)

		packages = self.get_packages ()
		if "glib-2.0" not in packages:
			packages.append ("glib-2.0")
			
		if "uselib" in args:
			args["uselib"].append (normalize_package_name("glib-2.0"))
		else:
			args["uselib"] = [normalize_package_name("glib-2.0")]
		
		args["packages"] = packages
		
		gir = self.get_gir ()
		if gir:
			args["gir"] = gir
		
		vapidirs = self.get_vapi_dirs ()
		if vapidirs:
			args["vapi_dirs"] = vapidirs
		
		return args

class DataTarget (ProjectTarget):
	def get_build_arguments (self):
		return {}

	def get_install_files (self):
		if "input" not in self._target:
			return []
		return self.get_input ()

	def get_install_path (self):
		return "${PREFIX}/share/" + self.get_name ()

class ProjectRequirement:
	def __init__ (self, name, env, requirement):
		self._name = name
		self._env = env
		self._requirement = requirement

	def _get_string_list (self, key):
		if key not in self._requirement:
			return []
		data = self._requirement[key]
		
		if isinstance (data, unicode):
			return [str(data),]
		elif isinstance (data, list):
			#TODO: Check if everything is str
			return [str(t) for t in data]
		else:
			return [str(data)]

	def get_name (self):
		return str(self._name)
	
	def get_type (self):
		if "type" not in self._requirement:
			#TODO: Type is required
			return

		return str(self._requirement["type"])
		
	def get_version (self):
		if "version" not in self._requirement:
			return
		return str(self._requirement["version"])
		
	def get_define (self):
		if "define" not in self._requirement:
			return None
		return str(self._requirement["define"])				
				
	def is_mandatory (self):
		if "mandatory" not in self._requirement:
			return False
			
		mandatory = resolve_value( str(self._requirement["mandatory"]), self._env )
		if "True" == mandatory:
			return True
		elif "False" == mandatory:
			return False
		else:
			#TODO: Warn about wrong mandatory 
			print "Wrong 'mandatory' value [" + str(self._requirement["mandatory"]) + "]" 
			pass

	def get_header (self):
		return self._get_string_list("header")
		
	def get_library (self):
		if "library" not in self._requirement:
				#TODO: Warn about missing library
			pass
			
		#return str(self._requirement["library"])
		return self._get_string_list("library")

	def get_env (self, env={}):
		env["CFLAGS"] = []
		env["CXXFLAGS"] = []
		env["CPPFLAGS"] = []
		env["LINKFLAGS"] = []
		if "cflags" in self._requirement and self._requirement["cflags"]:
			env["CFLAGS"] = self._get_string_list("cflags")
		if "cxxflags" in self._requirement and self._requirement["cxxflags"]:
			env["CXXFLAGS"] = self._get_string_list("cxxflags")
		if "cppflags" in self._requirement and self._requirement["cppflags"]:
			env["CPPFLAGS"] = self._get_string_list("cppflags")
		if "linkflags" in self._requirement and self._requirement["linkflags"]:
			env["LINKFLAGS"] = self._get_string_list("linkflags")

	def get_check_pkg_args (self):
		"WAF check_pkg arguments dictionary"
		args = {"package": self.get_name ()}
		
		#Correctly sets the version
		if self.get_version():
			version = self.get_version()
			if version.startswith ("= "):
				args["exact_version"] = str(version[2:])
			if version.startswith ("== "):
				args["exact_version"] = str(version[3:])
			elif version.startswith (">= "):
				args["atleast_version"] = str(version[3:])
			elif version.startswith ("<= "):
				args["max_version"] = str(version[3:])
			else:
				#FIXME: < and > are supported as an argument but not by waf
				#TODO: Warn that >= is recommended
				args["atleast_version"] = str(version)
				pass
				
		if self.get_type () == "package":
			args["mandatory"] = self.is_mandatory ()
			
		args["args"] = "--cflags --libs"
		
		args["uselib_store"] = normalize_package_name (self.get_name ())
		
		return args

	def get_check_lib_args (self):
		"WAF check_pkg arguments dictionary"
		args = { "lib" : self.get_name () }
		args["mandatory"] = self.is_mandatory ()
		if self.get_define():
			args["define_name"] = self.get_define()
		else:
			args["define_name"] = "HAVE_" + normalize_package_name (self.get_name ()) + "LIB"
		#args["uselib_store"] = normalize_package_name (self.get_name ())
		return args
				
	def get_check_func_args (self):
		"WAF check_pkg arguments dictionary"
		args = { "lib" : self.get_library () }
		args["header_name"] = self.get_header ()
		args["function_name"] = self.get_name ()
		args["mandatory"] = self.is_mandatory ()
		if self.get_define():
			args["define_name"] = self.get_define()
		else:
			args["define_name"] = "HAVE_" + normalize_package_name (self.get_name ())
		#args["uselib_store"] = normalize_package_name (self.get_name ())
		return args
		
	#TODO
	def get_check_program_args (self):
		"WAF check_pkg arguments dictionary"
		args = { "define_name" : normalize_package_name (self.get_name ()) }
				
		#if self.get_type () == "program":
		args["mandatory"] = self.is_mandatory ()
		#define_name="HAVE_TARLIB"
		#args["#define_name"] = normalize_package_name (self.get_name ())
		#args["uselib_store"] = normalize_package_name (self.get_name ())

		return args

class ProjectOption:
	def __init__ (self, name, option):
		self._name = str(name)
		self._option = option
	
		if not "default" in option:
			#TODO: Report lack of default value, default is mandatory
			return
			
		if "description" not in option:
			#TODO: Report lack of default description as a warning
			pass

		self._description = str(option["description"])
		self._default = str(option["default"])
		self._value = self._default

	def get_name (self):
		return self._name
	
	def get_description (self):
		return self._description
	
	def get_default (self):
		return self._default
	
	def get_value (self):
		return self._value
		
	def set_value (self, value):
		self._value = value
		
		
	def get_option_arguments (self):
		"WAF option arguments dictionary"
		return {"default": self.get_default (),
			"action": "store",
			"help":	self.get_description ()}

#Mapping between tools and target classes
TOOL_CLASS_MAP = {'cc':	 CcTarget,
		'c++':	CcTarget,
		'vala': ValaTarget,
		'data': DataTarget}

# Mapping between file extensions and tools
EXT_TOOL_MAP = {'cc':	 ('.c', '.h'),
		'c++':	('.cpp', '.cxx'),
		'vala': ('.vala', '.gs')}

# Mapping used when multiple tools are fond (using file extensions)
# Keys must be sorted tuples
MULTI_TOOL_MAP = {('c++', 'cc'):	'c++',
			('cc', 'vala'): 'vala'}

import os
import Utils
import sys
import platform
import Options
from buildj import *

APPNAME = None
VERSION = None

#BuilDj Tool -> Waf tool

####### Utils ##################################################################
def parse_project_file (project_file=DEFAULT_BUILDJ_FILE, env={}):
	try:
		project = ProjectFile (project_file, env)
		set_project_info(project)
	except ValueError, e:
		raise Utils.WscriptError (str(e), project_file)
	
	return project

def set_project_info (project):
    global APPNAME, VERSION
    APPNAME = project.get_project_name ()
    VERSION = project.get_project_version ()

def set_sysroot_env (prefix, env={}):
    env["sysroot"] = Options.options.sysroot
    env["CFLAGS"] += ['--sysroot=%s' % Options.options.sysroot]
    env["CXXFLAGS"] += ['--sysroot=%s' % Options.options.sysroot]
    env["LINKFLAGS"] += ['--sysroot=%s' % Options.options.sysroot]

def copy_env(env1={}, env2={}):
    env1["CFLAGS"] = env2["CFLAGS"]
    env1["CXXFLAGS"] = env2["CXXFLAGS"]
    env1["CPPFLAGS"] = env2["CPPFLAGS"]
    env1["LINKFLAGS"] = env2["LINKFLAGS"]

def set_crosscompile_env (prefix, env={}):
	for tool in CC_TOOLCHAIN:
		if tool not in env:
			env[tool] = prefix + "-" + CC_TOOLCHAIN[tool]
		# Setup various target file patterns
	
	#Windows Prefix/suffix (what about bcc and icc?)
	if ('mingw'  in prefix or
	    'msvc'   in prefix or
	    'cygwin' in prefix or
	    'msys'   in prefix):
		if not 'staticlib_PATTERN' in env:
			env['staticlib_PATTERN'] = '%s.lib'
		if not 'shlib_PATTERN' in env:
			env['shlib_PATTERN'] = '%s.dll'
		if not 'program_PATTERN' in env:
			env['program_PATTERN'] = '%s.exe'
		
	if 'PKG_CONFIG_LIBDIR' not in env:
		env['PKG_CONFIG_LIBDIR'] = '/usr/'+prefix+'/lib'

################################################################################
## WAF TARGETS 
################################################################################

def options (opt):
	project = parse_project_file ()

	#BuilDj options
	gr = opt.add_option_group('BuilDj options')
	gr.add_option('--buildj-file', action='store', default="project.yaml", help='Sets the BuilDj file.')	
	gr.add_option('--target-platform', action='store', default=None, help='Sets the target platform tuple used as a prefix for the gcc toolchain.')
	gr.add_option('--sysroot', action='store', default='', help='Sets the target platform sysroot directory.')

	#Project options
	gr = opt.add_option_group('Project options')
	for option in project.get_options ():
		gr.add_option("--"+option.get_name (), **option.get_option_arguments ())
	
	#Infered options
	included_tools = []
	for tool in project.get_tools ():
		tool = WAF_TOOLS[tool]
		if tool not in included_tools:
			opt.load(tool)
			#opt.tool_options (tool)
			included_tools.append (tool)

def configure (conf):
	#Cross compile tests
	if Options.options.target_platform:
		set_crosscompile_env (Options.options.target_platform, conf.env)
	
	if Options.options.sysroot:
		set_sysroot_env(Options.options.sysroot, conf.env)
	
	conf.env["host-os"] = sys.platform
	conf.env["host-arch"] = platform.machine()
	conf.env["host-system"] = platform.system()	
	
	project = parse_project_file (DEFAULT_BUILDJ_FILE, {})
	
	for option in project.get_options ():
		optname = option.get_name()
		conf.env['${' + optname + '}'] = getattr(Options.options, optname)
	
	project = parse_project_file (DEFAULT_BUILDJ_FILE, conf.env)
	
	for tool in project.get_tools ():
		conf.check_tool (WAF_TOOLS[tool])

	#We check all the tools required packages
	for package in project.get_packages_required ():
		conf.check_cfg (**package.get_check_pkg_args ())

	#We check all the tools required libraries
	for library in project.get_libraries_required ():
		conf.check(**library.get_check_lib_args ())

	#We check all the tools required function
	for func in project.get_functions_required ():
		cfgenv = {}
		bkpenv = {}
		func.get_env(cfgenv)
		copy_env(bkpenv, conf.env)
		copy_env(conf.env, cfgenv)
		conf.check(**func.get_check_func_args ())
		copy_env(conf.env, bkpenv)

	#We check all the tools' required programs
	#for program in project.get_programs_required ():
	#	a = { "mandatory" : "False" }
	#	conf.find_program ( 'md5sum2'  a )

	#FIXME: This should be done upstream
	if "vala" in project.get_tools():
		if not conf.env.HAVE_GLIB_2_0:
			conf.check_cfg (package="glib-2.0", mandatory=True)

	conf.write_config_header()

def build(bld):
	
	#print bld.env
	print "build"
	project = parse_project_file (DEFAULT_BUILDJ_FILE, bld.env)

	for target in project.get_targets ():
		args = target.get_build_arguments ()
		args['path'] = bld.srcnode.find_dir(target.get_path())
		bld.new_task_gen (**args)

		install_files = target.get_install_files ()
		if install_files:
			bld.install_files (target.get_install_path (), install_files)

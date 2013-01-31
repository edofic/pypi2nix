
import sys
from distutils2.pypi.simple import Crawler
from distutils2.version import suggest_normalized_version




def to_nixname(name):
    return name.replace('.', '_').replace('-', '_')
    result = ''
    for word in name.split('.'):
        if not name.startswith(word):
            word = word[0].upper() + word[1:]
        result += word
    return result


def to_dict(text):
    result = {}
    current_tree = []
    for line in text.split('\n'):
        if not line:
            continue

        egg = line.strip().split();
        egg_name, egg_version, egg_extra = egg[0], '', ''
        if len(egg) >= 2:
            egg_version = egg[1]
        if len(egg) >= 3:
            egg_extra = egg[2]
        egg_nixname = to_nixname(egg_name)

        tree_level = int(round((len(line) - len(line.lstrip(' '))) / 4.0))

        current_tree = current_tree[:tree_level]
        current_tree.append(egg_nixname)

        if egg_nixname.startswith('['):  # this mean we're dealing with extras
            if len(current_tree) >= 2:
                result[current_tree[-2]]['extras'].append(egg_nixname[1:-1])
            continue

        if len(current_tree) >= 2:
            result[current_tree[-2]]['requirements'].append(egg_nixname)

        if egg_nixname not in result:
            result[egg_nixname] = {
                'name': egg_name,
                'version': egg_version,
                'extras': [],
                'requirements': []
                }

        #to_dict(..., spaces=spaces+4)

    return result

PRE_TMPL = """
{ pkgs, python, buildPythonPackage }:

let plone42Packages = python.modules // rec {
  inherit python;
  inherit (pkgs) fetchurl stdenv;

"""

TMPL = """
  %(nixname)s = buildPythonPackage rec {
    name = "%(name)s";

    src = fetchurl {
      url = "%(url)s";
      %(hashname)s = "%(hashval)s";
    };
%(install_command)s%(build_inputs)s
    doCheck = false;

    meta = {
      maintainers = [
        stdenv.lib.maintainers.chaoflow
        stdenv.lib.maintainers.garbas
        stdenv.lib.maintainers.goibhniu
     ];
    };
  };
"""

POST_TMPL = """
}; in plone42Packages
"""

overwrite = {}
overwrite['pytz'] = {
    'nixname': 'pytz',
    'name': 'pytz-2012c',
    'url': 'http://pypi.python.org/packages/source/p/pytz/pytz-2012c.tar.gz',
    'hashname': 'md5',
    'hashval': '1aa85f072e3d34ae310665967a0ce053',
    'install_command': '',
    'build_inputs': '',
    'propagated_build_inputs': '',

    }
overwrite['elementtree'] = {
    'nixname': 'elementtree',
    'name': 'elementtree-1.2.7-20070827-preview',
    'url': 'http://effbot.org/media/downloads/elementtree-1.2.7-20070827-preview.zip',
    'hashname': 'md5',
    'hashval': '30e2fe5edd143f347e03a8baf5d60f8a',
    'install_command': '',
    'build_inputs': '',
    'propagated_build_inputs': '',
    }

# extra_deps = {
#     "zope_publisher" : ["pytz",],
#     "products_zsqlmethods": [ "products_standardcachemanagers", "products_pythonscripts", "products_mimetools", "products_mailhost", "products_externalmethod", "products_btreefolder2", "zope_viewlet", "zope_testbrowser", "zope_sendmail", "zope_ptresource", "zope_size", "zope_processlifetime", "zope_site"],
#     "five_localsitemanager": ["products_standardcachemanagers", "products_pythonscripts", "products_mimetools", "products_mailhost", "products_externalmethod", "products_btreefolder2", "zope_viewlet", "zope_testbrowser", "zope_sendmail", "zope_ptresource", "zope_size", "zope_processlifetime", "zope_site"],
# #tested one by one: # five_customerize products_standardcachemanagers products_pythonscripts products_mimetools products_mailhost products_externalmethod products_btreefolder2 zope_testbrowser zope_sendmail zope_ptresource zope_processlifetime zope_browsermenu zlog tempstorage initgroups docutils zopeundo products_zctextindex products_zcatalog products_ofsp multimapping missing 
# # broken: plone_browserlayer
#     "products_statusmessages" = [ "pytz", ],
# }

if __name__ == '__main__':
    eggs = to_dict(sys.stdin.read())
    #eggs = to_dict(open("depdump", "r").read())
    pypi = Crawler()
    bad_eggs = []

    print PRE_TMPL
    for nixname in sorted(eggs.keys()):
        if nixname == '(setuptools)': continue
        egg = eggs[nixname]
        version = suggest_normalized_version(egg['version'])
        name = egg['name']
        if egg['extras']:
            name += '-'.join(egg['extras'])
        name += '-' + egg['version']
        if egg['name'] not in overwrite:
            egg_release = pypi.get_release(egg['name'] + '==' + version)
            egg_dist = egg_release.dists['sdist'].url
            url = egg_dist['url']
            url = url.replace("http://a.pypi", "http://pypi")
            url = url.replace(name, "${name}")
            build_inputs = ''
            if url.endswith(".zip"):
                build_inputs = "\n    buildInputs = [ pkgs.unzip ];\n"
            propagated_build_inputs = ''
            if egg['requirements']:
                if 'setuptools' in egg['requirements']:
                    egg['requirements'].pop(egg['requirements'].index('setuptools'))
                    egg['requirements'] = ['pkgs.setuptools'] + egg['requirements']
                propagated_build_inputs = (
                    '\n    propagatedBuildInputs = [ %s ];\n' 
                    % ' '.join(egg['requirements'])
                )
            # install_command = ''
            # for req in egg['requirements']:
            #     if "setuptools" in req: continue
            #     for reqreq in eggs[req]['requirements']:
            #         if nixname in reqreq:
            #             propagated_build_inputs = ''
            install_command = """
    # circular dependencies
    installCommand = ''
      easy_install --always-unzip --no-deps --prefix="$out" .
    '';
"""
            print TMPL % {
                'nixname': nixname,
                'name': name,
                'url': url,
                'hashname': egg_dist['hashname'],
                'hashval': egg_dist['hashval'],
                'build_inputs': build_inputs,
                'propagated_build_inputs': propagated_build_inputs,
                'install_command': install_command,
                }
        else:
            print TMPL % overwrite[egg['name']]
    print POST_TMPL

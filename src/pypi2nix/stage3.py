import sys
import os
import click


DEFAULT_NIX = '''# generated using pypi2nix tool (version: %(version)s)
# See more at: https://github.com/garbas/pypi2nix
#
# COMMAND:
#   pypi2nix %(command_arguments)s
#

{ pkgs ? import <nixpkgs> {}
}:

let

  inherit (pkgs) makeWrapper;
  inherit (pkgs.stdenv.lib) fix' extends inNixShell;

  pythonPackages = import "${toString pkgs.path}/pkgs/top-level/python-packages.nix" {
    inherit pkgs;
    inherit (pkgs) stdenv;
    python = pkgs.%(python_version)s;
  };

  commonBuildInputs = %(extra_build_inputs)s;
  commonDoCheck = %(enable_tests)s;

  withPackages = pkgs':
    let
      pkgs = builtins.removeAttrs pkgs' ["__unfix__"];
      interpreter = pythonPackages.buildPythonPackage {
        name = "%(python_version)s-interpreter";
        buildInputs = [ makeWrapper ] ++ (builtins.attrValues pkgs);
        buildCommand = ''
          mkdir -p $out/bin
          ln -s ${pythonPackages.python.interpreter} $out/bin/${pythonPackages.python.executable}
          for dep in ${builtins.concatStringsSep " " (builtins.attrValues pkgs)}; do
            if [ -d "$dep/bin" ]; then
              for prog in "$dep/bin/"*; do
                if [ -f $prog ]; then
                  ln -s $prog $out/bin/`basename $prog`
                fi
              done
            fi
          done
          for prog in "$out/bin/"*; do
            wrapProgram "$prog" --prefix PYTHONPATH : "$PYTHONPATH"
          done
          pushd $out/bin
          ln -s ${pythonPackages.python.executable} python
          popd
        '';
        passthru.interpreter = pythonPackages.python;
      };
    in {
      __old = pythonPackages;
      inherit interpreter;
      mkDerivation = pythonPackages.buildPythonPackage;
      packages = pkgs;
      overrideDerivation = drv: f:
        pythonPackages.buildPythonPackage (drv.drvAttrs // f drv.drvAttrs);
      withPackages = pkgs'':
        withPackages (pkgs // pkgs'');
    };

  python = withPackages {};

  generated = import %(generated_file)s { inherit pkgs python commonBuildInputs commonDoCheck; };
  overrides = import %(overrides_file)s { inherit pkgs python; };

in python.withPackages (fix' (extends overrides generated))
'''

GENERATED_NIX = '''# generated using pypi2nix tool (version: %s)
#
# COMMAND:
#   pypi2nix %s
#

{ pkgs, python, commonBuildInputs ? [], commonDoCheck ? false }:

self: {
%s
}
'''

GENERATED_PACKAGE_NIX = '''
  "%(name)s" = python.mkDerivation {
    name = "%(name)s-%(version)s";
    src = %(fetch_expression)s;
    doCheck = commonDoCheck;
    buildInputs = commonBuildInputs;
    propagatedBuildInputs = %(propagatedBuildInputs)s;
    meta = with pkgs.stdenv.lib; {
      homepage = "%(homepage)s";
      license = %(license)s;
      description = "%(description)s";
    };
  };
'''

OVERRIDES_NIX = '''
{ pkgs, python }:

self: super: {
%s
}
'''


def main(packages_metadata,
         requirements_name,
         requirements_files,
         requirements_frozen,
         extra_build_inputs,
         enable_tests,
         python_version,
         current_dir,
         ):
    '''Create Nix expressions.
    '''

    default_file = os.path.join(current_dir, '{}.nix'.format(requirements_name))
    generated_file = os.path.join(current_dir, '{}_generated.nix'.format(requirements_name))
    overrides_file = os.path.join(current_dir, '{}_override.nix'.format(requirements_name))
    frozen_file = os.path.join(current_dir, '{}_frozen.txt'.format(requirements_name))

    version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
    with open(version_file) as f:
        version = f.read()

    metadata_by_name = {x['name'].lower(): x for x in packages_metadata}

    generated_packages_metadata = []
    for item in sorted(packages_metadata, key=lambda x: x['name']):
        propagatedBuildInputs = '[ ]'
        if item.get('deps'):
            deps = [x for x in item['deps'] if x.lower() in metadata_by_name.keys()]
            if deps:
                propagatedBuildInputs = "[\n%s\n    ]" % (
                    '\n'.join(sorted(
                        ['      self."%s"' % (metadata_by_name[x.lower()]['name'])
                        for x in deps if x not in [item['name']]
                    ])))
        fetch_type = item.get('fetch_type', None)
        if fetch_type == 'fetchgit':
            fetch_expression = 'pkgs.fetchgit { url = "%(url)s"; %(hash_type)s = "%(hash_value)s"; rev = "%(rev)s"; }' % dict(
                url=item['url'],
                hash_type=item['hash_type'],
                hash_value=item['hash_value'],
                rev=item['rev']
            )
        else:
            fetch_expression='pkgs.fetchurl { url = "%(url)s"; %(hash_type)s = "%(hash_value)s"; }' % dict(
                url=item['url'],
                hash_type=item['hash_type'],
                hash_value=item['hash_value'],
            )

        generated_packages_metadata.append(dict(
            name=item.get("name", ""),
            version=item.get("version", ""),
            fetch_expression=fetch_expression,
            propagatedBuildInputs=propagatedBuildInputs,
            homepage=item.get("homepage", ""),
            license=item.get("license", ""),
            description=item.get("description", ""),
        ))

    generated = GENERATED_NIX % (
        version, ' '.join(sys.argv[1:]), '\n\n'.join(
            GENERATED_PACKAGE_NIX % x for x in generated_packages_metadata))

    overrides = OVERRIDES_NIX % ""

    default = DEFAULT_NIX % dict(
        version=version,
        command_arguments=' '.join(sys.argv[1:]),
        python_version=python_version,
        extra_build_inputs=extra_build_inputs
            and "with pkgs; [ %s ]" % (' '.join(extra_build_inputs))
            or "[]",
        generated_file='.' + generated_file[len(current_dir):],
        overrides_file='.' + overrides_file[len(current_dir):],
        enable_tests=str(enable_tests).lower(),
    )

    with open(generated_file, 'w+') as f:
        f.write(generated.strip())
        click.echo('|-> writing %s' % generated_file)

    if not os.path.exists(overrides_file):
        with open(overrides_file, 'w+') as f:
            f.write(overrides.strip())
            click.echo('|-> writing %s' % overrides_file)

    with open(default_file, 'w+') as f:
        f.write(default.strip())

    with open(requirements_frozen) as f:
        frozen_content = f.read()

    with open(frozen_file, 'w+') as f:
        f.write(frozen_content)

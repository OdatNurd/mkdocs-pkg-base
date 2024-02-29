# Documentation Setup

The contents of this entire project are meant to be used as either the basis of
a brand new package, or plopped directly into an existing package to augment it
with documentation, as appropriate.

To that end, all that is strictly required is the `docs/` folder and the entry
in `.gitattributes` that stops it from being archived so that it does not end up
in the `sublime-package` file.


# Setup

Copy as much of this project as desired into the destination folder, or
alternately clone this as the basis of a new package, then blow away `.git` and
create repository as appropriate.

Edit `docs/mkdocs.yml`; the main part to edit is the per project configuration
that is at the top of the file. Secondarily, `PackageName` can be modified
everywhere, both in this file and in all of the Markdown files in the `doc`
folder, replacing it with the actual name.

The stub contents that are put in place should be edited to have actual good
content within them. The overall structure is set (but can be manipulated as
desired).


# Local Documentation

Development or browsing of documentation can be performed locally via the
following steps (the first of which you only need to perform once, naturally).

1. Switch to `docs/` and create/activate a virtual environment
2. use `pip install -r requirements.txt` to set up
3. use `mkdocs serve` to build and serve documentation.

Experience seems to dictate that changes to the configuration or the template
files requires you to stop and start the server again, but changes to the
content will be watched for automatically.


# Development and Production Deployments

The way the templates are set up, the instructions (outlined below) will
generate pages to two sites, one on `odatnurd.net` and one on `nurdlabs.net`,
both from specific branches (i.e. `master` and `develop`), and the version that
is deployed to `nurdlabs.net` will have a banner reminding people that they are
looking at prerelease documentation and not the official documentation.


# Deployment Instructions

Create a new CloudFlare pages project by connecting it to the GitHub repository
for the project, which should be based on the content of this repository (or
at least have the same base `docs/` folder content as this one).

The desired configuration is:

Branch Deployments:
    - Production Branch: `master`
        - Enable automatic production branch deployments
    - Preview branches:
        - Include `develop``
                - Exclude `all non production branches

    - Build configurations:
        - command: ./docs/cf_build.sh
        - output:  /docs/site
        - root:    /
        - Build on pull request: yes

    - Environment:
        - Production:
            EDIT_URI:       edit/master/docs
            PYTHON_VERSION: 3.11

        - Preview:
            EDIT_URI:       edit/develop/docs
            PYTHON_VERSION: 3.11
            THEME_OVERRIDE: overrides


Once this is done, pushes to either `master` or `develop` will trigger a build
by executing the build script and deploying the site. The configured environment
variables will tell it how to configure the build.


The next step is to set up the appropriate custom domains:

- Choose a project name (generally, the name of the package)
- Add two custom URL's:
    - `<project>.odatnurd.net`
    - `<project>.nurdlabs.net`

When added in this order, the first one will be considered the "production"
deployment, and should Just Work (tm). The second one is going to be bound to
the wrong thing, most likely.

Check the `CNAME` record for both domains; ensure that the one for the
`nurdlabs.net` domain is set to `develop.<project>.pages.dev` as the source;
this is what ties the domain to the specific branch that is set out above.

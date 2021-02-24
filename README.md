# geocore-pygeoapi
A pygeoapi provider for CGP's geoCore Metadata API. 

# Use case and components
[Pygeoapi](https://pygeoapi.io) is a python based server implementation of the OGC API suite of standards. This module adds the capability to interact with the [CGP GeoCore Metadata API](https://github.com/Canadian-Geospatial-Platform/CGP_METADATA_API), which offers access to a variety of metadata records. The geocore-pygeoapi provider is set up as a python project, having the core pygeoapi project as a dependency. This means that pygeoapi is deployed as part of the install of the geocore-pygeoapi provider project. 

# Versioning of the geocore-pygeoapi provider
Feature development takes place in the master branch. As soon as we have a stable version a tag 0.x will be placed which can be used for production deployments, until a next release is made available. Any version released would benefit from referencing a fixed pygeoapi release. In the geocare-pygeoapi master branch a reference is made to the master branch of pygeoapi (requirements.txt) 

# Deploy and run a master branch
To run locally (or remote) the master branch, it requires some specific steps. Setup.py doesn’t like the github syntax in requirements.txt, so you have to deactivate line 90 (install_requires) in setup.py and deploy requirements.txt manually. Then navigate to src/pygeoapi and run pygeoapi installation in that folder manually.


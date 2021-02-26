# geocore-pygeoapi
A pygeoapi provider for CGP's geoCore Metadata API. 

## Use case and components
[Pygeoapi](https://pygeoapi.io) is a Python based server implementation of the OGC API suite of standards. This module adds the capability to interact with the [CGP geoCore Metadata API](https://github.com/Canadian-Geospatial-Platform/CGP_METADATA_API), which offers access to a variety of metadata records. The geocore-pygeoapi provider is set up as a Python project, having the core pygeoapi project as a dependency. This means that pygeoapi is deployed as part of the install of the geocore-pygeoapi provider project. 

## Versioning of the geocore-pygeoapi provider
Feature development takes place in the main branch. As soon as we have a stable version a tag `0.x` will be set, which can be used for production deployments until a next release becomes available. For these future geocore-pygeoapi provider releases, it is recommended to tie them to a specific pygeoapi release. In the geocare-pygeoapi main branch a reference is made to the master branch of pygeoapi (`requirements.txt`).

## Deploy and run main branch
Running a local or remote geocore-pygeoapi provider requires some specific steps for now. Because `pip` doesn’t like the `-e` syntax in `requirements.txt` when it uses it from the `install_requires` line in `setup.py`, you have to deactivate line 90 (`install_requires`) in `setup.py` and run `pip install` with the `-r requirements.txt` option. Then navigate to src/pygeoapi and run pygeoapi installation in that folder manually (`pygeoapi serve`).  

Another - and perhaps easier - approach is to run the provided Docker compose script, which is configured to run geocore-pygeoapi on `localhost:5000`. This will use the latest pygeoapi image from Docker Hub.

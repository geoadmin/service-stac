# STAC POST /search endpoint example

## Disclaimer

This Readme file and the according Jupyter notebook might not stay in the service-stac repository but probably will be moved into another repo in the mid-term.

## Jupyter notebook

This [jupyter notebook](./assets/stac-search-endpoint-example.ipynb) serves as a simple example for using the STAC API's POST /search endpoint. For the sake of readability, some best practices, such as proper error handling, checking checksums of the downloaded files, and the like, are not (fully) implemented in this notebook.

## Preparation

For this notebook to work, you need a recent Python version installed. You further need to install the following dependencies, e.g. by running `pip install folium geopandas jupyter mapclassify matplotlib pandas requests xyzservices` or by creating a virtual environment, where those dependencies are installed.

## Jupyter notebooks

Please refer to the documentation on how to run Jupyter notebooks on your machine: https://docs.jupyter.org/en/latest/running.html
Some IDEs support Jupyter notebooks, when the according extensions are installed.

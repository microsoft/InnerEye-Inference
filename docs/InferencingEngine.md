# Inferencing Engine

**What does Inferencing do and the flow related to the architecture?**

Inferencing Engine works to transform the Nifti images to Dicom RT files. Inferencing Engine reads the Dicom Image from the Queue which is present in the byte form. The image is transformed into nifty image and pushes it to the Inferencing container where it send back the Nifti seg mask image. The Segmentation processor take the nifti images and transforms to Dicom RT file. These Dicom RT images are pushed to blob and the progress of this task is saved in Table storage.

@Mark - To help out
# Inferencing APIs

## Gateway Dicom – Inferencing API

Inferencing API is one the main component of the Inner Eye architecture. Currently we have set of API calls, which are grouped into several functional groups and its part of InnerEye Cloud (classic cloud service) application.
(As part of architecture, Inferencing API is highlighted as below)

![ash_architecture.png](https://dev.azure.com/msdsip/8520c5e0-ef36-49bc-983d-12972ea056e0/_apis/git/repositories/cecb2ded-12e0-46f2-a2fe-7bf99a94811f/Items?path=%2F.attachments%2Fash_architecture-461fa2d7-8655-4ce9-b5b9-e6572b51030f.png&download=false&resolveLfs=true&%24format=octetStream&api-version=5.0-preview.1&sanitize=true&versionDescriptor.version=wikiMaster)

Below is the distribution of set of API call into as per their functional groups. Out of which we are working on Point 4 Inferencing API also test Point 5 for health check.

**1. DICOM Configuration**

These APIs configure DICOM endpoints that the Gateway can work with as well as routing rules for data that comes from these endpoints.
These APIs configure DICOM endpoints that the Gateway can work with as well as routing rules for data that comes from these endpoints.
**OSS implementation:** the configuration will be done via JSON files. These APIs are scrapped.

*/api/v1/config/gateway/update* - Gets the expected version the Gateway should be updated to.
*/api/v1/config/gateway/receive* - Gets the current gateway "receive" configuration.
*/api/v1/config/gateway/processor* - Gets the current gateway "processor" configuration.
*/api/v1/config/gateway/destination/{callingAET}* - Gets the destination DicomEndPoint to send results to given the AET of the caller
*/api/v1/config/gateway/destination/{callingAET}/{calledAET}* - Gets the destination DicomEndPoint to send results to given the AET of the caller and the calling AET (the way our gateway is being called)
*/api/v1/config/aetconfig/{calledAET}/{callingAET}* - Download a collection of DICOM constraints based on called AET and calling AET

**2. Data Upload**

This API endpoint provides a way to upload data for persisting the images for subsequent machine learning.
**OSS implementation:** These API need to be updated to conform with DICOMWeb implementation.
*/api/v1/storage* - Upload DICOM series to long term storage. In V1 this API call needs to be replaced with a call to a DICOM Web STOW-RS

**3. Feedback**

These APIs facilitate a workflow where a corrected segmentation is sent back for further analysis. This is not used in V1; the APIs below should be removed.
OSS implementation: These API need to be removed
*/api/v1/feedback* - Upload a collection of DICOM files (segmentation masks).
*/ping* - check if API is still up. Keep for V1
*/api/ping* - check if API is still up, with authentication. Remove for V1

**4. Inferencing**

These APIs have to do with inferencing:
• Get the list of registered models
• Send image for inferencing
• Get progress
• Retrieve result

**OSS implementation:** Most of these APIs remain and are essential to V1 operation
**/api/v1/models** - Returns a list of all models from Azure model blob container. This call is not needed for V1 implementation. This part was under discussion and based on meetings and discussion, for demos we are going to used two static model configurations.
**/api/v1/models/{modelId}/segmentation/{segmentationId}** - Checks the segmentation status for a given segmentation of a given model.
**/api/v1/models/{modelId}/segmentation/{segmentationId}/result** - Gets the result for a completed segmentation.
**/api/v1/models/{modelId}/segmentation** - Starts a segmentation. The content of the request should be a compressed zip file with a list of DICOM files with a folder per ChannelId E.g. ct\1.dcm, flair\1.dcm

**5. Health check**

*/ping* - check if API is still up. Keep for V1
*/api/ping* - check if API is still up, with authentication. Remove for V1
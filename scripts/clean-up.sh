#!/bin/bash

aws s3api delete-objects \
    --bucket ${BUCKET_NAME} \
    --delete "$(aws s3api list-object-versions \
        --bucket "${BUCKET_NAME}" \
        --output=json \
        --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}')"

aws s3api delete-objects \
    --bucket ${BUCKET_NAME} \
    --delete "$(aws s3api list-object-versions \
        --bucket "${BUCKET_NAME}" \
        --output=json \
        --query='{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}')"

aws s3 rb s3://${BUCKET_NAME}

IMAGES_TO_DELETE=$(aws ecr list-images \
    --region $ECR_REGION \
    --repository-name $ECR_REPO \
    --query 'imageIds[*]' --output json)

aws ecr batch-delete-image \
    --region $ECR_REGION \
    --repository-name $ECR_REPO \
    --image-ids "$IMAGES_TO_DELETE" || true


#remove sec profile
# remove audit config
# remove audit roles

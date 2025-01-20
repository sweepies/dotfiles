function gcloud
    docker run --rm --volumes-from gcloud-config -v (pwd):/workdir -w /workdir gcr.io/google.com/cloudsdktool/google-cloud-cli gcloud $argv; 
  end
  
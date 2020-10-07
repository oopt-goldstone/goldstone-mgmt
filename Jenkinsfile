pipeline {
  agent any
 
  environment {
    DOCKER_REPO = 'gs-test'
  }

  stages {
    stage('Build') {
      steps {
          sh """
              apk add --update docker make
              git submodule update --init
              make builder np2
              make docker
              make image
              make debug-image
          """
      }
    }
  }
}

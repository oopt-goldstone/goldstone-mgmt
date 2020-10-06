pipeline {
  agent any
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

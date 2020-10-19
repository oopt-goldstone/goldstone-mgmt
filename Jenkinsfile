pipeline {
  agent any
 
  stages {
    stage('Setup') {
      steps {
          script {
              if (env.BRANCH_NAME == 'master' ) {
                  env.DOCKER_REPO = 'nlpldev'
              } else {
                  env.DOCKER_REPO = 'gs-test'
              }
          }
      }
    }
    stage('Build') {
      steps {
          sh """
              apk add --update docker make
              git submodule update --init
              git diff --compact-summary HEAD origin/master | (grep 'sm/\\|patches/\\|builder.Dockerfile' && make builder np2) || true
              make docker
              make image
              make debug-image
          """
      }
    }
  }
}

pipeline {
  agent any
 
  stages {
    stage('Setup') {
      steps {
          sh 'env'
          script {
              if (env.BRANCH_NAME == 'master' ) {
                  env.DOCKER_REPO = 'nlpldev'
                  env.BUILD_BUILDER = 1
              } else if ( env.BRANCH_NAME.startsWith('PR') ) {
                  env.DOCKER_REPO = 'gs-test'
                  env.BUILD_BUILDER = sh returnStatus: true, script: "git diff --compact-summary HEAD origin/master | grep -v 'sm/\\|patches/\\|builder.Dockerfile'"
              } else {
                  env.BUILD_BUILDER = 0
                  currentBuild.result = 'SUCCESS'
                  echo "no need to build ${env.BRANCH_NAME}"
                  sh "exit 0"
              }
          }
          sh """
              echo $env.BUILD_BUILDER
              echo $BUILD_BUILDER
          """
      }
    }
    stage('Build') {
      steps {
          sh """
              apk add --update docker make
              git submodule update --init
              ( [ $BUILD_BUILDER -eq 1 ] && make builder np2 ) || true
              make docker
              make image
              make debug-image
          """
      }
    }
  }
}

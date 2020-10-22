pipeline {
  agent any

  parameters {
    string(name: 'DEVICE', defaultValue: '10.10.10.114', description: 'IP address of the test device')
  }

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
          sh 'apk add --update docker make'
          sh 'git submodule update --init'
          sh '( [ $BUILD_BUILDER -eq 1 ] && make builder np2 ) || true'
          sh 'make docker'
          sh 'make image'
          sh 'make debug-image'
      }
    }

    stage('Load') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
      }
      steps {
        sh 'docker build -t gs-mgmt-test -f ci/docker/gs-mgmt-test.Dockerfile ci'

        timeout(time: 15, unit: 'MINUTES') {
            sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 ./ci/tools/load.py ${params.DEVICE}"
        }
      }
    }
  }

}

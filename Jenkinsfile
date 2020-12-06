pipeline {
  agent any

  parameters {
    string(name: 'DEVICE', defaultValue: '10.10.10.113', description: 'IP address of the test device')
    booleanParam(name: 'FORCE_BUILD_BUILDER', defaultValue: false, description: 'build builder image forcibly')
  }

  stages {
    stage('Setup') {
      steps {
          sh 'env'
          script {
              env.SKIP = 0
              if (env.BRANCH_NAME == 'master' ) {
                  env.DOCKER_REPO = 'nlpldev'
                  env.BUILD_BUILDER = 1
              } else if ( env.BRANCH_NAME.startsWith('PR') ) {
                  env.DOCKER_REPO = 'gs-test'
                  // if sm/, patches/, builder.Dockerfile, build_onlp.sh is updated
                  // build the builder
                  env.BUILD_BUILDER = sh(returnStatus: true, script: "git diff --compact-summary HEAD origin/master | grep 'sm/\\|patches/\\|builder.Dockerfile\\|build_onlp.sh'") ? 0 : 1
              } else {
                  env.SKIP = 1
                  env.BUILD_BUILDER = 0
                  currentBuild.result = 'SUCCESS'
                  echo "no need to build ${env.BRANCH_NAME}"
              }
              if ( params.FORCE_BUILD_BUILDER ) {
                  env.BUILD_BUILDER = 1
              }
          }
          sh 'env'
      }
    }

    stage('Lint') {
      steps {
          sh 'docker build -t gs-mgmt-test -f ci/docker/gs-mgmt-test.Dockerfile ci'
          sh "docker run -t -v `pwd`:`pwd` -w `pwd`/src/north/cli/gscli gs-mgmt-test bash -c 'exit \$(black -q --diff *.py | wc -l)'"
          sh "docker run -t -v `pwd`:`pwd` -w `pwd`/yang gs-mgmt-test bash -c 'pyang *.yang'"
      }
    }

    stage('Build') {
      when {
        environment name: 'SKIP', value: '0'
      }
      steps {
          sh 'apk add --update docker make python2'
          sh 'git submodule update --init'
          sh 'if [ $BUILD_BUILDER -eq 1 ] ; then make builder np2; fi'
          sh 'make snmpd'
          sh 'make docker'
          sh 'make image'
          sh 'make debug-image'
      }
    }

    stage('Load') {
      when {
        branch pattern: "^PR.*", comparator: "REGEXP"
        environment name: 'SKIP', value: '0'
      }
      steps {
        sh 'docker build -t gs-mgmt-test -f ci/docker/gs-mgmt-test.Dockerfile ci'

        timeout(time: 15, unit: 'MINUTES') {
            sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 ./ci/tools/load.py ${params.DEVICE}"
        }

        timeout(time: 15, unit: 'MINUTES') {
            sh "docker run -v /var/run/docker.sock:/var/run/docker.sock -t -v `pwd`:`pwd` -w `pwd` gs-mgmt-test python3 ./ci/tools/test.py ${params.DEVICE}"
        }
      }
    }
  }

  post {
    always {
      script {
        if ( env.BRANCH_NAME != 'master' ) {
          deleteDir() /* clean up our workspace */
        }
      }
    }
  }

}
